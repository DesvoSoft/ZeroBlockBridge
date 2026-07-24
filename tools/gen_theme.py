"""Generate assets/zbb_theme.json from CTk's blue.json structure, recolored to the ZBB dirt-block palette.

Run after changing palette values here (keep in sync with app/core/app_config.py):
    py tools/gen_theme.py
"""
import json
import os
import customtkinter

SRC = os.path.join(os.path.dirname(customtkinter.__file__), "assets", "themes", "blue.json")

with open(SRC, encoding="utf-8") as f:
    t = json.load(f)

# Palette
BG = ["#f8fafc", "#0b1120"]
CARD = ["#ffffff", "#243044"]
CARD_TOP = ["#eef2f7", "#2c3a52"]
BORDER = ["#cbd5e1", "#334155"]
INPUT_BG = ["#ffffff", "#0a0f1c"]
TEXT = ["#0f172a", "#e2e8f0"]
TEXT_DISABLED = ["#94a3b8", "#64748b"]
PLACEHOLDER = ["#94a3b8", "#64748b"]
PRIMARY = ["#65a30d", "#65a30d"]        # lime-600
PRIMARY_HOVER = ["#4d7c0f", "#4d7c0f"]  # lime-700
PRIMARY_DEEP = ["#4d7c0f", "#3f6212"]
GHOST_HOVER = ["#e2e8f0", "#334155"]
SCROLLBAR_BTN = ["gray55", "gray41"]
SCROLLBAR_BTN_HOVER = ["gray40", "gray53"]

t["CTk"]["fg_color"] = BG
t["CTkToplevel"]["fg_color"] = BG

t["CTkFrame"].update({"corner_radius": 10, "border_width": 0,
                      "fg_color": CARD, "top_fg_color": CARD_TOP, "border_color": BORDER})

t["CTkButton"].update({"corner_radius": 8, "border_width": 0,
                       "fg_color": PRIMARY, "hover_color": PRIMARY_HOVER, "border_color": BORDER,
                       "text_color": ["#ffffff", "#f8fafc"], "text_color_disabled": TEXT_DISABLED})

t["CTkLabel"].update({"text_color": TEXT})

t["CTkEntry"].update({"corner_radius": 8, "border_width": 1, "fg_color": INPUT_BG,
                      "border_color": BORDER, "text_color": TEXT,
                      "placeholder_text_color": PLACEHOLDER})

t["CTkCheckBox"].update({"corner_radius": 6, "border_width": 2, "fg_color": PRIMARY,
                         "border_color": ["#94a3b8", "#475569"], "hover_color": PRIMARY_HOVER,
                         "checkmark_color": ["#ffffff", "#f8fafc"], "text_color": TEXT,
                         "text_color_disabled": TEXT_DISABLED})

t["CTkSwitch"].update({"fg_color": ["#cbd5e1", "#334155"], "progress_color": PRIMARY,
                       "button_color": ["#ffffff", "#e2e8f0"], "button_hover_color": ["#f1f5f9", "#f8fafc"],
                       "text_color": TEXT, "text_color_disabled": TEXT_DISABLED})

t["CTkRadioButton"].update({"fg_color": PRIMARY, "border_color": ["#94a3b8", "#475569"],
                            "hover_color": PRIMARY_HOVER, "text_color": TEXT,
                            "text_color_disabled": TEXT_DISABLED})

t["CTkProgressBar"].update({"progress_color": PRIMARY, "fg_color": ["#e2e8f0", "#334155"],
                            "border_color": BORDER})

t["CTkSlider"].update({"fg_color": ["#e2e8f0", "#334155"], "progress_color": PRIMARY_DEEP,
                       "button_color": PRIMARY, "button_hover_color": PRIMARY_HOVER})

t["CTkOptionMenu"].update({"corner_radius": 8, "fg_color": ["#e2e8f0", "#0f172a"],
                           "button_color": PRIMARY, "button_hover_color": PRIMARY_HOVER,
                           "text_color": TEXT, "text_color_disabled": TEXT_DISABLED})

t["CTkComboBox"].update({"corner_radius": 8, "border_width": 1, "fg_color": INPUT_BG,
                         "border_color": BORDER, "button_color": ["#e2e8f0", "#334155"],
                         "button_hover_color": GHOST_HOVER, "text_color": TEXT,
                         "text_color_disabled": TEXT_DISABLED})

t["CTkScrollbar"].update({"fg_color": "transparent", "button_color": SCROLLBAR_BTN,
                          "button_hover_color": SCROLLBAR_BTN_HOVER})

t["CTkSegmentedButton"].update({"corner_radius": 8, "border_width": 2,
                                "fg_color": ["#e2e8f0", "#0f172a"],
                                "selected_color": PRIMARY, "selected_hover_color": PRIMARY_HOVER,
                                "unselected_color": ["#e2e8f0", "#0f172a"],
                                "unselected_hover_color": GHOST_HOVER,
                                "text_color": TEXT, "text_color_disabled": TEXT_DISABLED})

t["CTkTextbox"].update({"corner_radius": 8, "border_width": 0, "fg_color": INPUT_BG,
                        "border_color": BORDER, "text_color": TEXT,
                        "scrollbar_button_color": SCROLLBAR_BTN,
                        "scrollbar_button_hover_color": SCROLLBAR_BTN_HOVER})

t["CTkScrollableFrame"]["label_fg_color"] = CARD_TOP

t["DropdownMenu"].update({"fg_color": ["#eef2f7", "#243044"], "hover_color": GHOST_HOVER,
                          "text_color": TEXT})

t["CTkFont"]["Windows"] = {"family": "Segoe UI Variable Text", "size": 13, "weight": "normal"}

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(_repo_root, "assets", "zbb_theme.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(t, f, indent=2)
print("written", out)
print("keys:", list(t.keys()))
