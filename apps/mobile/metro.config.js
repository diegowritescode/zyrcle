// Learn more: https://docs.expo.dev/guides/customizing-metro
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);

// @zyrcle/client is a file: dependency (TypeScript source in packages/client). The repo does not
// use npm workspaces, because the web app and this app pin different React versions, so Metro has
// to be told to watch the linked folder.
config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, "../../packages/client")];

module.exports = config;
