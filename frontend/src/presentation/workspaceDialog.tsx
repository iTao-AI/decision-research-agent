import { useLayoutEffect, useRef, type FormEvent, type ReactNode } from "react";

export function WorkspaceDialog({ title, onClose, children, onSubmit }: {
  title: string;
  onClose: () => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  useLayoutEffect(() => {
    const element = dialog.current;
    if (!element || element.open) return;
    if (typeof element.showModal === "function") element.showModal();
    else {
      element.open = true;
      element.querySelector<HTMLElement>("input, button")?.focus();
    }
  }, []);

  return (
    <dialog className="dw-dialog" ref={dialog} aria-labelledby="dw-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}>
      <form onSubmit={onSubmit ?? ((event) => event.preventDefault())}>
        <h2 id="dw-dialog-title">{title}</h2>
        {children}
      </form>
    </dialog>
  );
}
