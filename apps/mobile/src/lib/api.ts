/** The shared Zyrcle API client (packages/client), bound to this build's API URL. */
import { createApi } from "@zyrcle/client";
import { API_URL } from "./config";

export const { api, liveUrl } = createApi(API_URL);
