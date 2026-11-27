import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import Fieldwork from "./fieldwork/Fieldwork";
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

const isFieldwork = /^\/fieldwork\/?$/.test(window.location.pathname);
if (isFieldwork) document.title = "DRA Fieldwork · 现场服务助手";

createRoot(root).render(
  <StrictMode>
    {isFieldwork ? <Fieldwork /> : <App />}
  </StrictMode>
);
