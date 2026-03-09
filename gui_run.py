from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from PIL import Image, ImageTk, ImageOps

from fishprep.pipeline import finalize_review_from_config, run_pipeline_from_config


class DuplicateReviewApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("fishprep Duplicate Review")
        self.root.geometry("1400x920")
        self.root.minsize(1200, 800)

        self.dataset_dir = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.jpeg_quality = tk.StringVar(value="90")
        self.max_size_mb = tk.StringVar(value="10")
        self.duplicate_tolerance = tk.StringVar(value="5")
        self.blur_threshold = tk.StringVar(value="5")
        self.enable_centering_check = tk.BooleanVar(value=False)
        self.centering_threshold = tk.StringVar(value="0.2")

        self.status_text = tk.StringVar(value="Set the folders in Settings, then run the analysis.")
        self.progress_text = tk.StringVar(value="Idle.")
        self.group_title = tk.StringVar(value="No duplicate group loaded.")
        self.reference_text = tk.StringVar(value="")
        self.candidate_text = tk.StringVar(value="")
        self.selected_candidate_path: str | None = None

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.groups: list[pd.DataFrame] = []
        self.current_group_index = 0
        self.current_group_duplicates = pd.DataFrame()
        self.duplicate_report = pd.DataFrame()
        self.decisions: dict[str, str] = {}
        self.output_dir: Path | None = None
        self.current_reference_row: pd.Series | None = None
        self.current_candidate_row: pd.Series | None = None
        self.reference_photo: ImageTk.PhotoImage | None = None
        self.candidate_photo: ImageTk.PhotoImage | None = None
        self.is_busy = False

        self._build_layout()
        self.root.after(150, self._poll_messages)

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, padding=12)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        ttk.Label(shell, textvariable=self.status_text).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.notebook = ttk.Notebook(shell)
        self.notebook.grid(row=1, column=0, sticky="nsew")

        settings_tab = ttk.Frame(self.notebook, padding=12)
        review_tab = ttk.Frame(self.notebook, padding=12)
        settings_tab.columnconfigure(1, weight=1)
        settings_tab.columnconfigure(3, weight=1)
        settings_tab.rowconfigure(6, weight=1)
        review_tab.columnconfigure(0, weight=1)
        review_tab.rowconfigure(0, weight=1)

        self.notebook.add(settings_tab, text="Settings")
        self.notebook.add(review_tab, text="Review")

        self._build_settings_tab(settings_tab)
        self._build_review_tab(review_tab)

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Dataset directory").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(parent, textvariable=self.dataset_dir).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 8))
        ttk.Button(parent, text="Browse", command=self.browse_dataset_dir).grid(row=0, column=3, sticky="e")

        ttk.Label(parent, text="Output directory").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(parent, textvariable=self.output_dir_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 8))
        ttk.Button(parent, text="Browse", command=self.browse_output_dir).grid(row=1, column=3, sticky="e")

        ttk.Label(parent, text="JPEG quality").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(parent, textvariable=self.jpeg_quality, width=12).grid(row=2, column=1, sticky="w", padx=(8, 24))

        ttk.Label(parent, text="Max size (MB)").grid(row=2, column=2, sticky="w")
        ttk.Entry(parent, textvariable=self.max_size_mb, width=12).grid(row=2, column=3, sticky="w")

        ttk.Label(parent, text="Duplicate tolerance").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(parent, textvariable=self.duplicate_tolerance, width=12).grid(row=3, column=1, sticky="w", padx=(8, 24))

        ttk.Label(parent, text="Blur threshold").grid(row=3, column=2, sticky="w")
        ttk.Entry(parent, textvariable=self.blur_threshold, width=12).grid(row=3, column=3, sticky="w")

        ttk.Checkbutton(parent, text="Enable centering check", variable=self.enable_centering_check).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )
        ttk.Label(parent, text="Centering threshold").grid(row=4, column=2, sticky="w")
        ttk.Entry(parent, textvariable=self.centering_threshold, width=12).grid(row=4, column=3, sticky="w")

        actions = ttk.Frame(parent)
        actions.grid(row=5, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.run_analysis_button = ttk.Button(actions, text="Run Analysis", command=self.run_analysis)
        self.run_analysis_button.pack(side="left")
        self.run_analysis_button.configure(default="active")
        self.load_review_button = ttk.Button(actions, text="Load Existing Review", command=self.load_existing_review)
        self.load_review_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open Review Tab", command=lambda: self.notebook.select(1)).pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(parent, text="Progress", padding=8)
        progress_frame.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.progress_text, justify="left").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(8, 0),
        )

        help_text = (
            "Set the dataset folder, output folder, and thresholds here.\n"
            "Exact duplicates are handled automatically. Duplicate tolerance controls how aggressively near-duplicate images are flagged for review in the GUI."
        )
        ttk.Label(parent, text=help_text, justify="left").grid(row=7, column=0, columnspan=4, sticky="nw", pady=(20, 0))

    def _build_review_tab(self, parent: ttk.Frame) -> None:
        vertical = ttk.Panedwindow(parent, orient="vertical")
        vertical.grid(row=0, column=0, sticky="nsew")

        comparison_panel = ttk.Frame(vertical, padding=4)
        comparison_panel.columnconfigure(0, weight=1)
        comparison_panel.columnconfigure(1, weight=1)
        comparison_panel.rowconfigure(0, weight=1)

        reference_frame = ttk.LabelFrame(comparison_panel, text="Reference Image", padding=8)
        reference_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        reference_frame.rowconfigure(0, weight=1)
        reference_frame.columnconfigure(0, weight=1)

        self.reference_image_label = ttk.Label(reference_frame, anchor="center")
        self.reference_image_label.grid(row=0, column=0, sticky="nsew")
        self.reference_image_label.bind("<Configure>", lambda _event: self._refresh_reference_image())
        ttk.Label(reference_frame, textvariable=self.reference_text, justify="left").grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        candidate_frame = ttk.LabelFrame(comparison_panel, text="Selected Candidate", padding=8)
        candidate_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.columnconfigure(0, weight=1)

        self.candidate_image_label = ttk.Label(candidate_frame, anchor="center")
        self.candidate_image_label.grid(row=0, column=0, sticky="nsew")
        self.candidate_image_label.bind("<Configure>", lambda _event: self._refresh_candidate_image())
        ttk.Label(candidate_frame, textvariable=self.candidate_text, justify="left").grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        review_panel = ttk.Frame(vertical, padding=4)
        review_panel.columnconfigure(0, weight=1)
        review_panel.rowconfigure(1, weight=1)

        header = ttk.Frame(review_panel)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(header, text="Previous", command=self.previous_group).pack(side="left")
        ttk.Button(header, text="Next", command=self.next_group).pack(side="left", padx=(6, 0))
        ttk.Label(header, textvariable=self.group_title).pack(side="left", padx=(12, 0))

        candidate_list_frame = ttk.LabelFrame(review_panel, text="Candidates", padding=8)
        candidate_list_frame.grid(row=1, column=0, sticky="nsew")
        candidate_list_frame.columnconfigure(0, weight=1)
        candidate_list_frame.rowconfigure(0, weight=1)

        columns = ("role", "filename", "decision", "quality_score", "phash_distance")
        self.candidate_tree = ttk.Treeview(candidate_list_frame, columns=columns, show="headings", height=14)
        self.candidate_tree.heading("role", text="Role")
        self.candidate_tree.heading("filename", text="Filename")
        self.candidate_tree.heading("decision", text="Decision")
        self.candidate_tree.heading("quality_score", text="Quality")
        self.candidate_tree.heading("phash_distance", text="pHash Dist")
        self.candidate_tree.column("role", width=90, anchor="center")
        self.candidate_tree.column("filename", width=320)
        self.candidate_tree.column("decision", width=110, anchor="center")
        self.candidate_tree.column("quality_score", width=90, anchor="e")
        self.candidate_tree.column("phash_distance", width=100, anchor="e")
        self.candidate_tree.grid(row=0, column=0, sticky="nsew")
        self.candidate_tree.bind("<<TreeviewSelect>>", self.on_candidate_selected)

        button_bar = ttk.Frame(review_panel)
        button_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(button_bar, text="Keep", command=lambda: self.set_current_decision("keep")).pack(side="left")
        ttk.Button(button_bar, text="Exclude", command=lambda: self.set_current_decision("exclude")).pack(
            side="left",
            padx=(6, 0),
        )
        ttk.Button(button_bar, text="Unsure", command=lambda: self.set_current_decision("unsure")).pack(
            side="left",
            padx=(6, 0),
        )
        ttk.Button(button_bar, text="Keep All In Group", command=lambda: self.set_group_decision("keep")).pack(
            side="left",
            padx=(18, 0),
        )
        ttk.Button(button_bar, text="Exclude All In Group", command=lambda: self.set_group_decision("exclude")).pack(
            side="left",
            padx=(6, 0),
        )
        ttk.Button(button_bar, text="Set As Reference", command=self.set_selected_as_reference).pack(
            side="left",
            padx=(18, 0),
        )
        ttk.Button(button_bar, text="Save and Finish", command=self.save_and_finish).pack(side="right")

        vertical.add(comparison_panel, weight=4)
        vertical.add(review_panel, weight=0)

    def browse_dataset_dir(self) -> None:
        selected = filedialog.askdirectory(title="Choose dataset directory")
        if selected:
            self.dataset_dir.set(selected)

    def browse_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Choose output directory")
        if selected:
            self.output_dir_var.set(selected)

    def _build_config(self) -> dict[str, object]:
        dataset_dir = self.dataset_dir.get().strip()
        output_dir = self.output_dir_var.get().strip()
        if not dataset_dir:
            raise ValueError("Dataset directory is required.")
        if not output_dir:
            raise ValueError("Output directory is required.")

        dataset_path = Path(dataset_dir).expanduser()
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset directory not found:\n{dataset_path}")

        return {
            "dataset_dir": str(dataset_path.resolve()),
            "output_dir": str(Path(output_dir).expanduser().resolve()),
            "jpeg_quality": int(self.jpeg_quality.get()),
            "max_size_mb": float(self.max_size_mb.get()),
            "duplicate_tolerance": int(self.duplicate_tolerance.get()),
            "phash_threshold": int(self.duplicate_tolerance.get()),
            "blur_threshold": float(self.blur_threshold.get()),
            "enable_centering_check": bool(self.enable_centering_check.get()),
            "centering_threshold": float(self.centering_threshold.get()),
        }

    def run_analysis(self) -> None:
        if self.is_busy:
            return
        try:
            config = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.status_text.set("Running automatic analysis. This may take a while for large datasets.")
        self._set_busy_state(True, "Running analysis and building review files...")
        worker = threading.Thread(target=self._run_analysis_worker, args=(config,), daemon=True)
        worker.start()

    def _run_analysis_worker(self, config: dict[str, object]) -> None:
        try:
            run_pipeline_from_config(config, finalize_outputs=False)
            output_dir = Path(str(config["output_dir"]))
            report, groups = self._read_duplicate_report(output_dir)
            self.message_queue.put(("analysis_complete", (output_dir, report, groups)))
        except Exception as exc:
            self.message_queue.put(("error", str(exc)))

    def load_existing_review(self) -> None:
        if self.is_busy:
            return
        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            messagebox.showerror("Missing output directory", "Set the output directory in Settings first.")
            return

        output_path = Path(output_dir).expanduser().resolve()
        self.status_text.set("Loading existing duplicate review report.")
        self._set_busy_state(True, "Loading review files...")
        worker = threading.Thread(target=self._load_existing_review_worker, args=(output_path,), daemon=True)
        worker.start()

    def _load_existing_review_worker(self, output_dir: Path) -> None:
        try:
            report, groups = self._read_duplicate_report(output_dir)
            self.message_queue.put(("load_complete", (output_dir, report, groups)))
        except Exception as exc:
            self.message_queue.put(("error", str(exc)))

    def _poll_messages(self) -> None:
        while not self.message_queue.empty():
            kind, payload = self.message_queue.get()
            if kind == "analysis_complete":
                output_dir, report, groups = payload
                self._apply_loaded_report(output_dir, report, groups)
                self.status_text.set("Automatic analysis finished. Review the duplicate groups and save decisions.")
                self._set_busy_state(False, "Analysis finished.")
                self.notebook.select(1)
            elif kind == "load_complete":
                output_dir, report, groups = payload
                self._apply_loaded_report(output_dir, report, groups)
                self.status_text.set("Loaded existing duplicate review report.")
                self._set_busy_state(False, "Review files loaded.")
                self.notebook.select(1)
            elif kind == "error":
                self.status_text.set("Analysis failed.")
                self._set_busy_state(False, "Operation failed.")
                messagebox.showerror("fishprep", str(payload))
        self.root.after(150, self._poll_messages)

    def _load_duplicate_report(self, output_dir: Path) -> None:
        report, groups = self._read_duplicate_report(output_dir)
        self._apply_loaded_report(output_dir, report, groups)

    def _read_duplicate_report(self, output_dir: Path) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
        report_path = output_dir / "duplicate_groups.csv"
        if not report_path.exists():
            raise FileNotFoundError(f"Duplicate report not found:\n{report_path}")

        duplicate_report = pd.read_csv(report_path)
        groups = [group.copy() for _, group in duplicate_report.groupby("group_id", sort=True)] if not duplicate_report.empty else []
        return duplicate_report, groups

    def _apply_loaded_report(self, output_dir: Path, duplicate_report: pd.DataFrame, groups: list[pd.DataFrame]) -> None:
        self.output_dir = output_dir
        self.decisions = {}
        self.duplicate_report = duplicate_report
        self.groups = groups

        if self.duplicate_report.empty:
            self.groups = []
            self.current_group_index = 0
            self.group_title.set("No suspected duplicates were found.")
            self.candidate_tree.delete(*self.candidate_tree.get_children())
            self.reference_text.set("")
            self.candidate_text.set("")
            self.current_reference_row = None
            self.current_candidate_row = None
            self.reference_image_label.configure(image="")
            self.candidate_image_label.configure(image="")
            return

        self.current_group_index = 0
        self._show_group()

    def _set_busy_state(self, is_busy: bool, message: str) -> None:
        self.is_busy = is_busy
        self.progress_text.set(message)
        if is_busy:
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()
        state = "disabled" if is_busy else "normal"
        self.run_analysis_button.configure(state=state)
        self.load_review_button.configure(state=state)

    def _show_group(self) -> None:
        if not self.groups:
            return

        group = self.groups[self.current_group_index]
        self.current_group_duplicates = group.copy()
        group_id = int(group["group_id"].iloc[0])
        duplicate_type = group["duplicate_type"].iloc[0]
        self.group_title.set(f"Group {self.current_group_index + 1}/{len(self.groups)}  |  ID {group_id}  |  {duplicate_type}")

        self.candidate_tree.delete(*self.candidate_tree.get_children())
        for row in group.itertuples(index=False):
            decision = self.decisions.get(row.path, "undecided" if row.role == "duplicate" else "reference")
            self.candidate_tree.insert(
                "",
                "end",
                iid=row.path,
                values=(
                    row.role,
                    row.filename,
                    decision,
                    self._format_number(getattr(row, "quality_score", None)),
                    self._format_number(getattr(row, "phash_distance_to_reference", None)),
                ),
            )

        reference = group.loc[group["role"] == "reference"].iloc[0]
        self.current_reference_row = reference
        self.reference_text.set(self._format_metadata(reference))
        self._refresh_reference_image()

        duplicate_rows = group.loc[group["role"] == "duplicate"]
        target_row = duplicate_rows.iloc[0] if not duplicate_rows.empty else reference
        self._select_candidate_row(target_row["path"])

    def on_candidate_selected(self, _event: object) -> None:
        selected = self.candidate_tree.selection()
        if not selected:
            return
        self._select_candidate_row(selected[0], update_tree=False)

    def _select_candidate_row(self, path: str, update_tree: bool = True) -> None:
        row = self.current_group_duplicates.loc[self.current_group_duplicates["path"] == path]
        if row.empty:
            return
        record = row.iloc[0]
        self.selected_candidate_path = path
        self.current_candidate_row = record
        self.candidate_text.set(self._format_metadata(record))
        self._refresh_candidate_image()
        if update_tree:
            self.candidate_tree.selection_set(path)
            self.candidate_tree.focus(path)

    def set_current_decision(self, decision: str) -> None:
        if not self.selected_candidate_path:
            return
        row = self.current_group_duplicates.loc[self.current_group_duplicates["path"] == self.selected_candidate_path].iloc[0]
        if row["role"] != "duplicate":
            return
        self.decisions[self.selected_candidate_path] = decision
        self._update_tree_decision(self.selected_candidate_path, decision)
        self.candidate_text.set(self._format_metadata(row))

    def set_group_decision(self, decision: str) -> None:
        for row in self.current_group_duplicates.itertuples(index=False):
            if row.role != "duplicate":
                continue
            self.decisions[row.path] = decision
            self._update_tree_decision(row.path, decision)

        if self.selected_candidate_path:
            selected = self.current_group_duplicates.loc[self.current_group_duplicates["path"] == self.selected_candidate_path]
            if not selected.empty:
                self.candidate_text.set(self._format_metadata(selected.iloc[0]))

    def set_selected_as_reference(self) -> None:
        if not self.selected_candidate_path or self.current_group_duplicates.empty:
            return

        selected_row = self.current_group_duplicates.loc[self.current_group_duplicates["path"] == self.selected_candidate_path]
        if selected_row.empty:
            return

        selected_record = selected_row.iloc[0]
        if selected_record["role"] == "reference":
            return

        current_reference = self.current_group_duplicates.loc[self.current_group_duplicates["role"] == "reference"]
        if current_reference.empty:
            return

        old_reference_path = current_reference.iloc[0]["path"]
        new_reference_path = selected_record["path"]
        self._set_group_reference(old_reference_path, new_reference_path)
        self._show_group()

    def _set_group_reference(self, old_reference_path: str, new_reference_path: str) -> None:
        active_group = self.groups[self.current_group_index].copy()
        active_group.loc[active_group["path"] == old_reference_path, "role"] = "duplicate"
        active_group.loc[active_group["path"] == new_reference_path, "role"] = "reference"
        active_group["reference_path"] = new_reference_path
        self.groups[self.current_group_index] = active_group

        if not self.duplicate_report.empty:
            group_id = active_group["group_id"].iloc[0]
            duplicate_type = active_group["duplicate_type"].iloc[0]
            group_mask = (self.duplicate_report["group_id"] == group_id) & (
                self.duplicate_report["duplicate_type"] == duplicate_type
            )
            self.duplicate_report.loc[group_mask & (self.duplicate_report["path"] == old_reference_path), "role"] = "duplicate"
            self.duplicate_report.loc[group_mask & (self.duplicate_report["path"] == new_reference_path), "role"] = "reference"
            self.duplicate_report.loc[group_mask, "reference_path"] = new_reference_path

        old_reference_decision = self.decisions.get(old_reference_path)
        self.decisions.pop(new_reference_path, None)
        if old_reference_decision == "reference":
            self.decisions.pop(old_reference_path, None)

    def _update_tree_decision(self, path: str, decision: str) -> None:
        current_values = list(self.candidate_tree.item(path, "values"))
        if not current_values:
            return
        current_values[2] = decision
        self.candidate_tree.item(path, values=current_values)

    def previous_group(self) -> None:
        if not self.groups:
            return
        self.current_group_index = (self.current_group_index - 1) % len(self.groups)
        self._show_group()

    def next_group(self) -> None:
        if not self.groups:
            return
        self.current_group_index = (self.current_group_index + 1) % len(self.groups)
        self._show_group()

    def save_decisions(self) -> None:
        if self.output_dir is None:
            messagebox.showinfo("No report", "Run the analysis or load an existing review first.")
            return

        should_save = messagebox.askyesno("Confirm save", "Confirm save?")
        if not should_save:
            return

        rows = self._decision_rows()
        output_path = self.output_dir / "duplicate_review_decisions.csv"
        pd.DataFrame(rows).to_csv(output_path, index=False)
        self.status_text.set(f"Saved review decisions to {output_path}")
        messagebox.showinfo("Saved", f"Decisions saved to:\n{output_path}")

    def save_and_finish(self) -> None:
        if self.output_dir is None:
            messagebox.showinfo("No report", "Run the analysis or load an existing review first.")
            return

        should_save = messagebox.askyesno("Confirm save", "Save decisions and finish review?")
        if not should_save:
            return

        self.finish_review()

    def finish_review(self) -> None:
        if self.output_dir is None:
            messagebox.showinfo("No report", "Run the analysis or load an existing review first.")
            return

        try:
            config = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        decisions = pd.DataFrame(self._decision_rows())
        decisions_path = self.output_dir / "duplicate_review_decisions.csv"
        decisions.to_csv(decisions_path, index=False)
        try:
            finalize_review_from_config(config, decisions=decisions)
        except Exception as exc:
            messagebox.showerror("Finish failed", str(exc))
            return

        self.status_text.set("Final catalog and output folders were created from the reviewed decisions.")
        messagebox.showinfo(
            "Review finished",
            "Saved the reviewed catalog and created the standard, duplicates, and low_quality folders.",
        )

    def _decision_rows(self) -> list[dict[str, object]]:
        rows = []
        for group in self.groups:
            for row in group.itertuples(index=False):
                rows.append(
                    {
                        "group_id": row.group_id,
                        "duplicate_type": row.duplicate_type,
                        "role": row.role,
                        "reference_path": row.reference_path,
                        "path": row.path,
                        "filename": row.filename,
                        "specimen_id": row.specimen_id,
                        "decision": self.decisions.get(row.path, "reference" if row.role == "reference" else "undecided"),
                    }
                )
        return rows

    def _refresh_reference_image(self) -> None:
        self.reference_photo = self._load_photo(self.current_reference_row, self.reference_image_label)
        self.reference_image_label.configure(image=self.reference_photo)

    def _refresh_candidate_image(self) -> None:
        self.candidate_photo = self._load_photo(self.current_candidate_row, self.candidate_image_label)
        self.candidate_image_label.configure(image=self.candidate_photo)

    def _load_photo(self, row: pd.Series | None, container: ttk.Label) -> ImageTk.PhotoImage | None:
        if row is None:
            return None

        image_path = self._best_preview_path(row)
        if image_path is None:
            return None

        try:
            image = Image.open(image_path)
            width = max(container.winfo_width(), 100)
            height = max(container.winfo_height(), 100)
            image = ImageOps.contain(image, (width, height))
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _best_preview_path(self, row: pd.Series) -> Path | None:
        for column in ("new_path", "working_path", "path"):
            value = row.get(column)
            if isinstance(value, str) and value:
                candidate = Path(value)
                if candidate.exists():
                    return candidate
        return None

    def _format_metadata(self, row: pd.Series) -> str:
        lines = [
            f"Filename: {row.get('filename', '')}",
            f"Role: {row.get('role', '')}",
            f"Quality Score: {self._format_number(row.get('quality_score'))}",
            f"Difference Score: {self._format_number(row.get('phash_distance_to_reference'))}",
        ]
        decision = self.decisions.get(
            row.get("path"),
            "reference" if row.get("role") == "reference" else "undecided",
        )
        lines.append(f"Review decision: {decision}")
        return "\n".join(lines)

    @staticmethod
    def _format_number(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)


def main() -> None:
    root = tk.Tk()
    app = DuplicateReviewApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
