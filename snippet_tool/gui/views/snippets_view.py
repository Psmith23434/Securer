"""
Snippets view — main snippet manager panel.

Layout:
  Left panel  : search bar + scrollable snippet card list
  Right panel : detail/edit panel with title, content, tags, action buttons
"""
import customtkinter as ctk
from snippet_tool.gui.theme import (
    COLORS, FONT_BODY, FONT_MONO,
    SIZE_XS, SIZE_SM, SIZE_BASE, SIZE_LG, SIZE_XL,
    SP2, SP3, SP4, SP5, SP6, SP8,
    RADIUS_MD, RADIUS_LG, RADIUS_XL,
)
from snippet_tool.core.snippet_logic import (
    get_all_snippets, create_snippet, update_snippet,
    delete_snippet, search_snippets,
)


class SnippetsView(ctk.CTkFrame):
    def __init__(self, master, toast_fn, **kwargs):
        mode = ctk.get_appearance_mode().lower()
        c = COLORS[mode]
        super().__init__(master, fg_color=c["bg"], corner_radius=0, **kwargs)
        self._toast = toast_fn
        self._mode = mode
        self._selected_id: int | None = None
        self._snippets: list[dict] = []
        self._card_widgets: list[ctk.CTkFrame] = []
        self._build()
        self._load_snippets()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        c = COLORS[self._mode]
        self.columnconfigure(0, weight=0, minsize=280)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ---- Left panel ----
        self._left = ctk.CTkFrame(self, fg_color=c["surface"], corner_radius=0)
        self._left.grid(row=0, column=0, sticky="nsew")
        self._left.rowconfigure(1, weight=1)
        self._left.columnconfigure(0, weight=1)

        # Search + New button row
        search_row = ctk.CTkFrame(self._left, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew", padx=SP4, pady=(SP5, SP3))
        search_row.columnconfigure(0, weight=1)

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search())
        self._search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self._search_var,
            placeholder_text="Search snippets…",
            font=(FONT_BODY, SIZE_SM),
            corner_radius=RADIUS_MD,
            height=34,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, SP3))

        ctk.CTkButton(
            search_row,
            text="+",
            font=(FONT_BODY, SIZE_LG, "bold"),
            width=34, height=34,
            corner_radius=RADIUS_MD,
            fg_color=c["primary"],
            hover_color=c["primary_hover"],
            text_color=c["text_inverse"],
            command=self._new_snippet,
        ).grid(row=0, column=1)

        # Scrollable list
        self._list_frame = ctk.CTkScrollableFrame(
            self._left,
            fg_color="transparent",
            corner_radius=0,
        )
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=SP3, pady=(0, SP4))
        self._list_frame.columnconfigure(0, weight=1)

        # ---- Right panel ----
        self._right = ctk.CTkFrame(self, fg_color=c["bg"], corner_radius=0)
        self._right.grid(row=0, column=1, sticky="nsew")
        self._build_detail_panel()

    def _build_detail_panel(self):
        c = COLORS[self._mode]
        r = self._right
        for w in r.winfo_children():
            w.destroy()
        r.columnconfigure(0, weight=1)
        r.rowconfigure(2, weight=1)

        # Title
        ctk.CTkLabel(
            r, text="Title",
            font=(FONT_BODY, SIZE_SM), text_color=c["text_muted"],
            anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=SP8, pady=(SP8, SP2))

        self._title_var = ctk.StringVar()
        self._title_entry = ctk.CTkEntry(
            r,
            textvariable=self._title_var,
            placeholder_text="Snippet title…",
            font=(FONT_BODY, SIZE_LG, "bold"),
            height=40,
            corner_radius=RADIUS_MD,
        )
        self._title_entry.grid(row=1, column=0, sticky="ew", padx=SP8, pady=(0, SP4))

        ctk.CTkLabel(
            r, text="Content",
            font=(FONT_BODY, SIZE_SM), text_color=c["text_muted"],
            anchor="w"
        ).grid(row=2, column=0, sticky="nw", padx=SP8, pady=(0, SP2))

        self._content_box = ctk.CTkTextbox(
            r,
            font=(FONT_MONO, SIZE_BASE),
            corner_radius=RADIUS_MD,
            wrap="word",
        )
        self._content_box.grid(row=3, column=0, sticky="nsew", padx=SP8, pady=(0, SP4))
        r.rowconfigure(3, weight=1)

        # Tags row
        ctk.CTkLabel(
            r, text="Tags (comma-separated)",
            font=(FONT_BODY, SIZE_SM), text_color=c["text_muted"],
            anchor="w"
        ).grid(row=4, column=0, sticky="w", padx=SP8, pady=(0, SP2))

        self._tags_var = ctk.StringVar()
        ctk.CTkEntry(
            r,
            textvariable=self._tags_var,
            placeholder_text="python, regex, work…",
            font=(FONT_BODY, SIZE_SM),
            height=32,
            corner_radius=RADIUS_MD,
        ).grid(row=5, column=0, sticky="ew", padx=SP8, pady=(0, SP5))

        # Action buttons
        btn_row = ctk.CTkFrame(r, fg_color="transparent")
        btn_row.grid(row=6, column=0, sticky="ew", padx=SP8, pady=(0, SP8))

        ctk.CTkButton(
            btn_row, text="Copy",
            font=(FONT_BODY, SIZE_SM),
            height=34, corner_radius=RADIUS_MD,
            fg_color=c["surface_offset"],
            hover_color=c["surface_2"],
            text_color=c["text"],
            command=self._copy_content,
        ).pack(side="left", padx=(0, SP3))

        ctk.CTkButton(
            btn_row, text="Save",
            font=(FONT_BODY, SIZE_SM),
            height=34, corner_radius=RADIUS_MD,
            fg_color=c["primary"],
            hover_color=c["primary_hover"],
            text_color=c["text_inverse"],
            command=self._save_snippet,
        ).pack(side="left", padx=(0, SP3))

        ctk.CTkButton(
            btn_row, text="Delete",
            font=(FONT_BODY, SIZE_SM),
            height=34, corner_radius=RADIUS_MD,
            fg_color="transparent",
            hover_color=c["error_subtle"],
            text_color=c["error"],
            border_width=1,
            border_color=c["border"],
            command=self._delete_snippet,
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            r, text="",
            font=(FONT_BODY, SIZE_XS),
            text_color=c["text_faint"],
            anchor="e",
        )
        self._status_label.grid(row=7, column=0, sticky="e", padx=SP8, pady=(0, SP4))

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------

    def _load_snippets(self, query: str = ""):
        if query.strip():
            self._snippets = search_snippets(query)
        else:
            self._snippets = get_all_snippets()
        self._render_list()

    def _render_list(self):
        c = COLORS[self._mode]
        # Clear existing cards
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._card_widgets.clear()

        if not self._snippets:
            ctk.CTkLabel(
                self._list_frame,
                text="No snippets yet.\nClick + to create one.",
                font=(FONT_BODY, SIZE_SM),
                text_color=c["text_faint"],
                justify="center",
            ).pack(pady=SP8 * 3)
            return

        for snippet in self._snippets:
            card = self._make_card(snippet)
            card.pack(fill="x", pady=2)
            self._card_widgets.append(card)

    def _make_card(self, snippet: dict) -> ctk.CTkFrame:
        c = COLORS[self._mode]
        is_selected = snippet["id"] == self._selected_id
        card = ctk.CTkFrame(
            self._list_frame,
            fg_color=c["sidebar_active"] if is_selected else c["surface"],
            corner_radius=RADIUS_MD,
            cursor="hand2",
        )
        card.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            card,
            text=snippet["title"] or "Untitled",
            font=(FONT_BODY, SIZE_BASE, "bold"),
            text_color=c["text"],
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w", padx=SP4, pady=(SP3, SP2))

        preview = snippet["content"][:80].replace("\n", " ")
        if len(snippet["content"]) > 80:
            preview += "…"
        ctk.CTkLabel(
            card,
            text=preview,
            font=(FONT_BODY, SIZE_XS),
            text_color=c["text_muted"],
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=SP4, pady=(0, SP3))

        # Bind click on all children
        for widget in [card, title]:
            widget.bind("<Button-1>", lambda e, sid=snippet["id"]: self._select(sid))

        return card

    def _select(self, snippet_id: int):
        self._selected_id = snippet_id
        snippet = next((s for s in self._snippets if s["id"] == snippet_id), None)
        if not snippet:
            return
        self._title_var.set(snippet["title"])
        self._content_box.delete("1.0", "end")
        self._content_box.insert("1.0", snippet["content"])
        self._tags_var.set(", ".join(snippet.get("tags", [])))
        self._status_label.configure(text=f"Updated: {snippet['updated'][:10]}")
        self._render_list()  # Refresh card highlight

    def _on_search(self):
        self._load_snippets(self._search_var.get())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _new_snippet(self):
        s = create_snippet("New Snippet", "")
        self._selected_id = s["id"]
        self._load_snippets()
        self._select(s["id"])
        self._title_entry.focus()

    def _save_snippet(self):
        if not self._selected_id:
            self._new_snippet()
            return
        tags = [t.strip() for t in self._tags_var.get().split(",") if t.strip()]
        content = self._content_box.get("1.0", "end").rstrip()
        update_snippet(self._selected_id,
                       title=self._title_var.get(),
                       content=content,
                       tags=tags)
        self._load_snippets()
        self._toast("Saved!", "success")

    def _copy_content(self):
        content = self._content_box.get("1.0", "end").rstrip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self._toast("Copied to clipboard!", "success")

    def _delete_snippet(self):
        if not self._selected_id:
            return
        delete_snippet(self._selected_id)
        self._selected_id = None
        self._title_var.set("")
        self._content_box.delete("1.0", "end")
        self._tags_var.set("")
        self._status_label.configure(text="")
        self._load_snippets()
        self._toast("Snippet deleted.", "warning")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def update_theme(self, mode: str):
        self._mode = mode
        c = COLORS[mode]
        self.configure(fg_color=c["bg"])
        self._left.configure(fg_color=c["surface"])
        self._right.configure(fg_color=c["bg"])
        self._build_detail_panel()
        self._render_list()
