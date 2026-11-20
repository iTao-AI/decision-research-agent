import { screen, within } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";

type User = ReturnType<typeof userEvent.setup>;

export async function openExistingResearch(user: User, runId: string) {
  await user.click(screen.getByRole("button", { name: "查看已有研究" }));
  const dialog = within(screen.getByRole("dialog", { name: "查看已有研究" }));
  await user.type(dialog.getByRole("textbox", { name: "运行编号" }), runId);
  await user.click(dialog.getByRole("button", { name: "打开研究" }));
}

export async function useEnglish(user: User) {
  await user.click(screen.getByRole("button", { name: "设置" }));
  await user.click(screen.getByRole("button", { name: "English" }));
  const dialog = within(screen.getByRole("dialog", { name: "Settings" }));
  await user.click(dialog.getByRole("button", { name: "Close" }));
}
