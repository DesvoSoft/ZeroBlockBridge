import customtkinter as ctk


class Toast:
    """Non-blocking notification overlay positioned at bottom-right of parent window."""

    _active = None
    _after_id = None

    @classmethod
    def show(cls, parent, message, duration=4000, color="#f97316"):
        cls.dismiss()

        toast = ctk.CTkToplevel(parent)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.lift()

        frame = ctk.CTkFrame(toast, fg_color=color, corner_radius=8)
        frame.pack(fill="both", expand=True)

        label = ctk.CTkLabel(
            frame, text=message, text_color="white",
            font=("Roboto", 12), padx=16, pady=10,
        )
        label.pack()

        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        tw = 380
        th = 44
        x = px + pw - tw - 16
        y = py + ph - th - 16
        toast.geometry(f"{tw}x{th}+{x}+{y}")

        cls._active = toast
        cls._after_id = toast.after(duration, cls.dismiss)

    @classmethod
    def dismiss(cls):
        if cls._after_id and cls._active:
            try:
                cls._active.after_cancel(cls._after_id)
            except Exception:
                pass
        if cls._active:
            try:
                cls._active.destroy()
            except Exception:
                pass
        cls._active = None
        cls._after_id = None
