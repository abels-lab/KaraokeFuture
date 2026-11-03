"""The party's own style on top of the theme: what the DJ Co-Pilot's set_style tool changes
(services/agent/tools_style.py), also on the Settings page. All `client` settings, applied live
on every screen by static/look.js and static/style-fx.css; "Reset group" undoes the lot."""
from core.settings_kinds import NOW, _n, _s

HEX = r"#[0-9a-fA-F]{6}"

STYLE_SPECS = [
    _s("style_accent_hex", "style", "Custom highlight colour", "", "text",
       "Any colour as #rrggbb for titles, buttons and sung words. Empty: the colour preset above.",
       NOW, client=True, max_len=7, allow_empty=True, pattern=HEX, pattern_help="a colour like #ff00aa"),
    _s("style_font", "style", "Font", "theme", "choice",
       "The lettering of titles and lyrics.", NOW, client=True,
       choices=[["theme", "Theme font"], ["rounded", "Rounded"], ["condensed", "Tall & condensed"],
                ["serif", "Classic serif"], ["mono", "Typewriter"], ["handwritten", "Handwritten"]]),
    _s("style_title_effect", "style", "Title effect", "none", "choice",
       "How the party title and song titles move.", NOW, client=True,
       choices=[["none", "None"], ["glow", "Soft glow"], ["neon", "Flickering neon"], ["rainbow", "Rainbow"],
                ["bounce", "Bounce"], ["wobble", "Wobble"]]),
    _s("style_background", "style", "Background effect", "theme", "choice",
       "Drawn over the theme's background, behind everything else.", NOW, client=True,
       choices=[["theme", "Theme only"], ["aurora", "Aurora"], ["disco", "Disco lights"], ["stars", "Stars"],
                ["scanlines", "Retro scanlines"], ["dark", "Plain dark"]]),
    _n("style_glow", "style", "Glow", 0, 0, 100, 5, "%",
       "Neon glow around titles and sung words.", NOW, client=True),
    _n("style_corners", "style", "Corner rounding", 100, 0, 200, 10, "%",
       "0% gives square cards and buttons, 200% very round ones.", NOW, client=True),
    _n("style_pulse", "style", "Beat pulse", 0, 0, 100, 5, "%",
       "How much titles and cards pulse with the music (0 = still).", NOW, client=True),
    _s("custom_css", "style", "Custom CSS", "", "text",
       "Extra CSS for every screen, for whatever the options above can't do. Nothing may load from outside "
       "(no url(), @import, comments or '<'). Clear it to undo.", NOW, client=True, allow_empty=True, css=True,
       max_len=4000),
]
