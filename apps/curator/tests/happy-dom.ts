import { GlobalRegistrator } from "@happy-dom/global-registrator";

if (typeof globalThis.window === "undefined") {
  GlobalRegistrator.register({ url: "http://localhost/" });
}

// React 19 warns from `act` unless the test environment declares itself one.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
