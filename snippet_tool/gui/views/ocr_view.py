"""
OCR view — capture text from screen or clipboard.

Features:
  - Paste image from clipboard and run OCR
  - Capture full screen OCR
  - Result text area with copy + save-as-snippet buttons
  - Backend selector: Tesseract / EasyOCR
"""
import customtkinter as ctk
from snippet_tool.gui.theme import (
    COLORS, FONT_BODY, FONT_MONO,
    SIZE_SM, SIZE_BASE, SIZE_LG,
    SP2, SP3, SP4, SP5, SP6, SP8,
    RADIUS_MD,
)
from snippet_tool.core.ocr_engine import (
    extract_text_from_clipboard,
    extract_text_from_screenshot,
    extract_text_from_file,
)
from snippet_tool.core.snippet_logic import create_snippet


class OCRView(ctk.CTkFrame):
    def __init__(self, master, toast_fn, **kwargs):
        mode = ctk.get_appearance_mode().lower()
        c = COLORS[mode]
        super().__init__(master, fg_color=c["bg"], corner_radius=0, **kwargs)
        self._toast = toast_fn
        self._mode = mode
        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        c = COLORS[self._mode]
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=SP8, pady=(SP8, SP5))

        ctk.CTkLabel(
            header,
            text="OCR Capture",
            font=(FONT_BODY, SIZE_LG, "bold"),
            text_color=c["text"],
            anchor="w",
        ).pack(side="left")

        # Backend selector
        ctk.CTkLabel(
            header, text="Backend:",
            font=(FONT_BODY, SIZE_SM),
            text_color=c["text_muted"],
        ).pack(side="right", padx=(SP4, SP2))

        self._backend_var = ctk.StringVar(value="tesseract")
        ctk.CTkSegmentedButton(
            header,
            values=["tesseract", "easyocr"],
            variable=self._backend_var,
            font=(FONT_BODY, SIZE_SM),
        ).pack(side="right")

        # Action buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=SP8, pady=(0, SP5))

        ctk.CTkButton(
            btn_row,
            text="\u229e  Paste from Clipboard",
            font=(FONT_BODY, SIZE_SM),
            height=36, corner_radius=RADIUS_MD,
            fg_color=c["primary"],
            hover_color=c["primary_hover"],
            text_color=c["text_inverse"],
            command=self._from_clipboard,
        ).pack(side="left", padx=(0, SP3))

        ctk.CTkButton(
            btn_row,
            text="\u2315  Capture Screen",
            font=(FONT_BODY, SIZE_SM),
            height=36, corner_radius=RADIUS_MD,
            fg_color=c["surface_offset"],
            hover_color=c["surface_2"],
            text_color=c["text"],
            command=self._from_screen,
        ).pack(side="left", padx=(0, SP3))

        ctk.CTkButton(
            btn_row,
            text="\u1f4c2  Open File…",
            font=(FONT_BODY, SIZE_SM),
            height=36, corner_radius=RADIUS_MD,
            fg_color=c["surface_offset"],
            hover_color=c["surface_2"],
            text_color=c["text"],
            command=self._from_file,
        ).pack(side="left")

        # Result text area
        self._result_box = ctk.CTkTextbox(
            self,
            font=(FONT_MONO, SIZE_BASE),
            corner_radius=RADIUS_MD,
            wrap="word",
        )
        self._result_box.grid(row=2, column=0, sticky="nsew", padx=SP8, pady=(0, SP5))
        self._result_box.insert("1.0", "OCR result will appear here…")
        self._result_box.configure(state="disabled")

        # Bottom actions
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.grid(row=3, column=0, sticky="ew", padx=SP8, pady=(0, SP8))

        ctk.CTkButton(
            action_row, text="Copy Result",
            font=(FONT_BODY, SIZE_SM),
            height=34, corner_radius=RADIUS_MD,
            fg_color=c["surface_offset"],
            hover_color=c["surface_2"],
            text_color=c["text"],
            command=self._copy_result,
        ).pack(side="left", padx=(0, SP3))

        ctk.CTkButton(
            action_row, text="Save as Snippet",
            font=(FONT_BODY, SIZE_SM),
            height=34, corner_radius=RADIUS_MD,
            fg_color=c["primary"],
            hover_color=c["primary_hover"],
            text_color=c["text_inverse"],
            command=self._save_as_snippet,
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            action_row, text="",
            font=(FONT_BODY, SIZE_SM),
            text_color=c["text_muted"],
        )
        self._status_label.pack(side="right")

    # ------------------------------------------------------------------
    # OCR actions
    # ------------------------------------------------------------------

    def _set_result(self, text: str):
        self._result_box.configure(state="normal")
        self._result_box.delete("1.0", "end")
        self._result_box.insert("1.0", text)
        self._result_box.configure(state="disabled")

    def _from_clipboard(self):
        self._status_label.configure(text="Running OCR…")
        self.update()
        text = extract_text_from_clipboard()
        if text is None:
            self._toast("No image found in clipboard.", "warning")
            self._status_label.configure(text="")
            return
        self._set_result(text)
        char_count = len(text)
        self._status_label.configure(text=f"{char_count} chars extracted")
        self._toast("OCR complete.", "success")

    def _from_screen(self):
        self._status_label.configure(text="Capturing screen…")
        self.update()
        text = extract_text_from_screenshot()
        self._set_result(text)
        self._status_label.configure(text=f"{len(text)} chars extracted")
        self._toast("Screen OCR complete.", "success")

    def _from_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"), ("All", "*.*")]
        )
        if not path:
            return
        self._status_label.configure(text="Running OCR…")
        self.update()
        backend = self._backend_var.get()
        text = extract_text_from_file(path, backend=backend)
        self._set_result(text)
        self._status_label.configure(text=f"{len(text)} chars extracted")
        self._toast("File OCR complete.", "success")

    def _copy_result(self):
        text = self._result_box.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self._toast("Copied!", "success")

    def _save_as_snippet(self):
        text = self._result_box.get("1.0", "end").strip()
        if not text:
            self._toast("Nothing to save.", "warning")
            return
        title = text[:40].split("\n")[0] or "OCR Result"
        create_snippet(title=title, content=text, tags=["ocr"])
        self._toast("Saved as snippet!", "success")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def update_theme(self, mode: str):
        self._mode = mode
        c = COLORS[mode]
        self.configure(fg_color=c["bg"])
