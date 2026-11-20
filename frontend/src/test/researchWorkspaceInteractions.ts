import { screen, within } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";

type User = ReturnType<typeof userEvent.setup>;

export async function openExistingResearch(user: User, runId: string, language: "zh" | "en" = "zh") {
  const [lookup, id, open] = language === "zh"
    ? ["查找研究", "运行编号", "打开研究"] : ["Find research", "Run ID", "Open research"];
  await user.click(screen.getByRole("button", { name: lookup }));
  const dialog = within(screen.getByRole("dialog", { name: lookup }));
  await user.type(dialog.getByRole("textbox", { name: id }), runId);
  await user.click(dialog.getByRole("button", { name: open }));
}

export async function useEnglish(user: User) {
  await user.click(screen.getByRole("button", { name: "服务已连接，打开连接设置" }));
  await user.click(screen.getByRole("button", { name: "English" }));
  const dialog = within(screen.getByRole("dialog", { name: "Connection settings" }));
  await user.click(dialog.getByRole("button", { name: "Close" }));
}
