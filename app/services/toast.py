import customtkinter as ctk


class _ToastWindow:
    """Non-blocking notification overlay at bottom-right of parent window."""

    def __init__(self):
        self._toast = None
        self._after_id = None

    def show(self, parent, message, duration=4000, color="#f97316"):
        self.dismiss()

        toast = ctk.CTkToplevel(parent)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.lift()
        toast.attributes("-alpha", 0.95)

        frame = ctk.CTkFrame(toast, fg_color=color, corner_radius=8)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame, text=message, text_color="white",
            font=("Roboto", 12), padx=16, pady=10,
        ).pack()

        parent.update_idletasks()
        toast.update_idletasks()
        tw = toast.winfo_reqwidth()
        th = toast.winfo_reqheight()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = parent.winfo_rootx() + pw - tw - 16
        y = parent.winfo_rooty() + ph - th - 16
        toast.geometry(f"{tw}x{th}+{x}+{y}")

        self._toast = toast
        self._after_id = toast.after(duration, self._destroy)

    def _destroy(self):
        if self._toast:
            try:
                self._toast.destroy()
            except Exception:
                pass
        self._toast = None
        self._after_id = None

    def dismiss(self):
        if self._after_id and self._toast:
            try:
                self._toast.after_cancel(self._after_id)
            except Exception:
                pass
            self._destroy()


Toast = _ToastWindow()
