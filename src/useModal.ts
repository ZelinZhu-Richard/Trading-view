import { useLayoutEffect, useRef } from 'react';

/** Close before removal so the native modal lifecycle restores its opening control. */
export function useModal() {
  const ref = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const node = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    node?.showModal();
    return () => {
      node?.close();
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);
  return ref;
}
