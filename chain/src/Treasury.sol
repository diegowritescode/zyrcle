// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {SafeCast} from "@openzeppelin/contracts/utils/math/SafeCast.sol";

/// @dev Subnet-EVM NativeMinter precompile. The Treasury must be enabled on its allow list.
interface INativeMinter {
    function mintNativeCoin(address addr, uint256 amount) external;
}

/// @title Zyrcle Treasury
/// @notice Mints ZYR, the native coin of ZyrcleChain (1 ZYR = 1 COP, 1e18 wei = 1 peso), and only
///         against pesos that were actually received: seed capital or the distributable part of a
///         confirmed sale of material. See docs/architecture.md, section 8.
///
///         Invariant: `minted <= backing` at all times.
///
///         Residents are paid in two steps, the way cooperatives pay farmers:
///         1. an advance when their deposit is verified, capped per deposit and per resident per day;
///         2. a settlement when the bag holding their material is sold: their pro-rata share of the
///            sale minus the advance. If the advance was larger than the share, the difference is
///            absorbed by the reserve and never clawed back.
///
///         The pro-rata shares are computed off chain from the traceability data; `reportHash`
///         anchors the published report so anyone can recompute them.
contract Treasury is AccessControl, Pausable {
    INativeMinter public constant NATIVE_MINTER = INativeMinter(0x0200000000000000000000000000000000000001);

    /// @notice Records pesos received (seed capital, sales) and tunes advance limits.
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    /// @notice The backend's hot key: pays advances and settlements within the limits above.
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    uint16 public constant BPS = 10_000;

    struct Shares {
        uint16 residents;
        uint16 collector;
        uint16 operations;
    }

    struct Sale {
        uint128 amount;
        uint128 residentsPart;
        uint128 collectorPart;
        uint128 residentsSettled;
        uint128 collectorPaid;
        bytes32 evidence;
    }

    /// @notice Pesos (in wei-ZYR) that ZYR may be minted against.
    uint256 public backing;
    /// @notice ZYR minted by this contract.
    uint256 public minted;
    uint256 public seedCapital;
    /// @notice The operations share of sales: stays in pesos, never minted, not part of `backing`.
    uint256 public operationsRevenue;

    Shares public shares;
    uint256 public maxAdvancePerDeposit;
    uint256 public dailyAdvanceCap;

    mapping(bytes32 ref => bool) public seedRecorded;
    mapping(bytes32 depositId => uint256) public advanceOf;
    mapping(bytes32 depositId => bool) public depositSettled;
    mapping(address resident => mapping(uint256 day => uint256)) public advancedOn;
    mapping(bytes32 saleId => Sale) public sales;

    event SeedCapitalRecorded(bytes32 indexed ref, uint256 amount);
    event SaleRecorded(
        bytes32 indexed saleId,
        uint256 amount,
        uint256 residentsPart,
        uint256 collectorPart,
        uint256 operationsPart,
        bytes32 evidence
    );
    event AdvancePaid(bytes32 indexed depositId, address indexed resident, uint256 amount);
    event DepositSettled(
        bytes32 indexed saleId, bytes32 indexed depositId, address indexed resident, uint256 share, uint256 payout
    );
    event ResidentsSettled(bytes32 indexed saleId, uint256 totalShares, uint256 totalPayout, bytes32 reportHash);
    event CollectorPaid(bytes32 indexed saleId, address indexed collector, uint256 amount);
    event SharesChanged(uint16 residents, uint16 collector, uint16 operations);
    event AdvanceLimitsChanged(uint256 maxAdvancePerDeposit, uint256 dailyAdvanceCap);

    error ZeroAmount();
    error ZeroAddress();
    error AlreadyRecorded(bytes32 id);
    error UnknownSale(bytes32 saleId);
    error UnbackedMint(uint256 requested, uint256 available);
    error AdvanceAlreadyPaid(bytes32 depositId);
    error AdvanceTooLarge(uint256 amount, uint256 max);
    error DailyCapExceeded(address resident, uint256 wouldBe, uint256 cap);
    error DepositAlreadySettled(bytes32 depositId);
    error ResidentsPartExceeded(bytes32 saleId, uint256 wouldBe, uint256 part);
    error CollectorPartExceeded(bytes32 saleId, uint256 wouldBe, uint256 part);
    error InvalidShares();
    error InvalidLimits();
    error LengthMismatch();

    constructor(address admin, Shares memory initialShares, uint256 maxAdvance, uint256 dailyCap) {
        if (admin == address(0)) revert ZeroAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _setShares(initialShares);
        _setAdvanceLimits(maxAdvance, dailyCap);
    }

    // ------------------------------------------------------------------ pesos in

    function recordSeedCapital(bytes32 ref, uint256 amount) external onlyRole(OPERATOR_ROLE) {
        if (amount == 0) revert ZeroAmount();
        if (seedRecorded[ref]) revert AlreadyRecorded(ref);
        seedRecorded[ref] = true;
        seedCapital += amount;
        backing += amount;
        emit SeedCapitalRecorded(ref, amount);
    }

    /// @notice A collection center paid `amount` for a bag and the payment reached the bank.
    function recordSale(bytes32 saleId, uint256 amount, bytes32 evidence) external onlyRole(OPERATOR_ROLE) {
        if (amount == 0) revert ZeroAmount();
        if (sales[saleId].amount != 0) revert AlreadyRecorded(saleId);
        Shares memory s = shares;
        uint256 residentsPart = amount * s.residents / BPS;
        uint256 collectorPart = amount * s.collector / BPS;
        uint256 operationsPart = amount - residentsPart - collectorPart;
        sales[saleId] = Sale({
            amount: SafeCast.toUint128(amount),
            residentsPart: SafeCast.toUint128(residentsPart),
            collectorPart: SafeCast.toUint128(collectorPart),
            residentsSettled: 0,
            collectorPaid: 0,
            evidence: evidence
        });
        backing += residentsPart + collectorPart;
        operationsRevenue += operationsPart;
        emit SaleRecorded(saleId, amount, residentsPart, collectorPart, operationsPart, evidence);
    }

    // ------------------------------------------------------------------ ZYR out

    function payAdvance(bytes32 depositId, address resident, uint256 amount)
        external
        onlyRole(ORACLE_ROLE)
        whenNotPaused
    {
        if (resident == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (advanceOf[depositId] != 0) revert AdvanceAlreadyPaid(depositId);
        if (depositSettled[depositId]) revert DepositAlreadySettled(depositId);
        if (amount > maxAdvancePerDeposit) revert AdvanceTooLarge(amount, maxAdvancePerDeposit);
        uint256 day = block.timestamp / 1 days;
        uint256 today = advancedOn[resident][day] + amount;
        if (today > dailyAdvanceCap) revert DailyCapExceeded(resident, today, dailyAdvanceCap);

        advanceOf[depositId] = amount;
        advancedOn[resident][day] = today;
        _mint(resident, amount);
        emit AdvancePaid(depositId, resident, amount);
    }

    /// @notice Pay residents their share of a sale, minus the advances already paid.
    /// @param shareAmounts Each deposit's pro-rata share of the sale's residents part.
    function settleResidents(
        bytes32 saleId,
        bytes32[] calldata depositIds,
        address[] calldata residents,
        uint256[] calldata shareAmounts,
        bytes32 reportHash
    ) external onlyRole(ORACLE_ROLE) whenNotPaused {
        if (depositIds.length != residents.length || depositIds.length != shareAmounts.length) {
            revert LengthMismatch();
        }
        Sale storage sale = sales[saleId];
        if (sale.amount == 0) revert UnknownSale(saleId);

        uint256 totalShares;
        uint256 totalPayout;
        for (uint256 i; i < depositIds.length; ++i) {
            totalShares += shareAmounts[i];
            totalPayout += _settleDeposit(saleId, depositIds[i], residents[i], shareAmounts[i]);
        }
        uint256 settled = sale.residentsSettled + totalShares;
        if (settled > sale.residentsPart) revert ResidentsPartExceeded(saleId, settled, sale.residentsPart);
        sale.residentsSettled = SafeCast.toUint128(settled);
        emit ResidentsSettled(saleId, totalShares, totalPayout, reportHash);
    }

    function payCollector(bytes32 saleId, address collector, uint256 amount)
        external
        onlyRole(ORACLE_ROLE)
        whenNotPaused
    {
        if (collector == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        Sale storage sale = sales[saleId];
        if (sale.amount == 0) revert UnknownSale(saleId);
        uint256 paid = sale.collectorPaid + amount;
        if (paid > sale.collectorPart) revert CollectorPartExceeded(saleId, paid, sale.collectorPart);
        sale.collectorPaid = SafeCast.toUint128(paid);
        _mint(collector, amount);
        emit CollectorPaid(saleId, collector, amount);
    }

    // ------------------------------------------------------------------ administration

    function setShares(Shares calldata newShares) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _setShares(newShares);
    }

    function setAdvanceLimits(uint256 maxAdvance, uint256 dailyCap) external onlyRole(OPERATOR_ROLE) {
        _setAdvanceLimits(maxAdvance, dailyCap);
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    /// @notice ZYR that can still be minted.
    function available() external view returns (uint256) {
        return backing - minted;
    }

    // ------------------------------------------------------------------ internals

    function _settleDeposit(bytes32 saleId, bytes32 depositId, address resident, uint256 share)
        private
        returns (uint256 payout)
    {
        if (resident == address(0)) revert ZeroAddress();
        if (depositSettled[depositId]) revert DepositAlreadySettled(depositId);
        depositSettled[depositId] = true;
        uint256 advance = advanceOf[depositId];
        payout = share > advance ? share - advance : 0;
        _mint(resident, payout);
        emit DepositSettled(saleId, depositId, resident, share, payout);
    }

    function _mint(address to, uint256 amount) private {
        if (amount == 0) return;
        if (minted + amount > backing) revert UnbackedMint(amount, backing - minted);
        minted += amount;
        NATIVE_MINTER.mintNativeCoin(to, amount);
    }

    function _setShares(Shares memory s) private {
        if (uint256(s.residents) + s.collector + s.operations != BPS) revert InvalidShares();
        shares = s;
        emit SharesChanged(s.residents, s.collector, s.operations);
    }

    function _setAdvanceLimits(uint256 maxAdvance, uint256 dailyCap) private {
        if (maxAdvance == 0 || dailyCap < maxAdvance) revert InvalidLimits();
        maxAdvancePerDeposit = maxAdvance;
        dailyAdvanceCap = dailyCap;
        emit AdvanceLimitsChanged(maxAdvance, dailyCap);
    }
}
