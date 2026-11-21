import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";
import "./workspace.css";
import "./workspaceHome.css";
import "./workspacePaper.css";
import "./workspaceJourneyStatus.css";
import "./workspaceReading.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element #root was not found.");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
