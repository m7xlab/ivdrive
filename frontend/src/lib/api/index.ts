import { hasAuthFlag, setAuthFlag, clearAuthFlag, clearTokens } from "./core";
import { authApi } from "./auth";
import { adminApi } from "./admin";
import { settingsApi } from "./settings";
import { vehiclesApi } from "./vehicles";
import { statisticsApi } from "./statistics";
import { geoApi } from "./geo";
import { integrationsApi } from "./integrations";

export const api = {
  hasAuthFlag,
  setAuthFlag,
  clearAuthFlag,
  clearTokens,
  ...authApi,
  ...adminApi,
  ...settingsApi,
  ...vehiclesApi,
  ...statisticsApi,
  ...geoApi,
  ...integrationsApi,
};

// Also export individual modules in case components want to import them directly later
export * from "./core";
export * from "./auth";
export * from "./admin";
export * from "./settings";
export * from "./vehicles";
export * from "./statistics";
export * from "./geo";
export * from "./integrations";
