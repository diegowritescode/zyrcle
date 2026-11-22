# ADR 0011: Hosts and sites

- Status: accepted (2026-11-22)

## Context
A container belonged to a "residence": a name, opening hours and spots per hour. The first real
host will be a university with several campuses ([roadmap](../roadmap-v1.md)). It is one institution
with one agreement, and it is a party to the money (a share of every sale, ADR 0013) and to the
impact reports (M5). A campus is a place with its own hours and containers. "Residence" described
neither.

## Decision
- **A host is the institution; a site is a place it runs.** `host` has a name, a kind
  (`university`, `residential`, `business`, `public`) and, from ADR 0013 on, the address its share
  is paid to. `site` is what `residence` was (name, opening hours, spots per container and hour)
  plus the host it belongs to. Containers belong to a site.
- **Participants are not tied to a site.** One account works at every site of every host, as
  before.
- **Migration without loss.** Table `residence` becomes `site`. Each existing residence gets a host
  of kind `residential` with the same name and the same id, so the mapping needs no lookup table and
  every id already handed out stays valid.
- **Public views per host and per site.** `GET /v1/hosts` and `GET /v1/hosts/{id}/dashboard` give a
  host's totals and each of its sites. `GET /v1/sites/{id}/dashboard` is what the residence
  dashboard was, plus its host.
- **Old names kept for one release.** The resident apps already installed read `residence_id`,
  `residence_name`, `/v1/residences` and `/v1/residences/{id}/dashboard`. Those stay as aliases of
  the site fields and routes until the apps in use have moved to the new names, and are marked
  deprecated in the code. Operator routes are only called by our own tools, so they are renamed
  outright.

## Consequences
- Every place that said "residence" now says "site" in code and "sede" in the apps.
- The demo becomes a university with two campuses. The seed renames the old demo residence instead
  of creating a second set of containers, so earlier demo deposits now count toward the first
  campus.
- A host with a single site shows the same numbers on both dashboards; that is expected.
