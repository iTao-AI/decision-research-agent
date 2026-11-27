import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.removeItem("dra.workspace.backend");
});
