import { useId, useLayoutEffect, useRef, type ReactNode } from "react";

export function WorkspaceDrawer({ title, closeLabel, active, onClose, children }: {
  title: string;
  closeLabel: string;
  active: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const titleId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    if (active) heading.current?.focus({ preventScroll: true });
  }, [active]);

  return <aside className="dw-drawer" role="region" aria-labelledby={titleId} hidden={!active}
    onKeyDown={(event) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        onClose();
      }
    }}>
    <div className="dw-drawer-heading">
      <h2 id={titleId} ref={heading} tabIndex={-1}>{title}</h2>
      <button className="dw-outline" type="button" onClick={onClose}>{closeLabel}</button>
    </div>
    <div className="dw-drawer-body">{children}</div>
  </aside>;
}
