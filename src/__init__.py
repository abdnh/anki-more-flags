import json
import sys
from typing import Any, Dict, Optional, Sequence, Tuple, Union, cast

from anki.cards import Card, CardId
from anki.collection import Collection, OpChangesWithCount, SearchNode
from anki.hooks import wrap
from aqt import appVersion, colors, gui_hooks, mw
from aqt.browser import (
    Browser,
    CellRow,
    ItemId,
    SidebarItem,
    SidebarItemType,
    SidebarTreeView,
)
from aqt.flags import Flag, FlagManager
from aqt.operations import CollectionOp
from aqt.qt import *
from aqt.reviewer import Reviewer
from aqt.theme import ColoredIcon
from aqt.utils import qtMenuShortcutWorkaround, tooltip, tr
from aqt.webview import WebContent

try:
    from aqt.browser.table import adjusted_bg_color
except ImportError:

    def adjusted_bg_color(color: Tuple[str, str]) -> Tuple[str, str]:  # type: ignore
        return color


from .consts import ADDON_DIR

sys.path.append(str(ADDON_DIR / "vendor"))

from .config import CustomFlag, config
from .gui.config import ConfigDialog

anki_version = tuple(int(p) for p in appVersion.split("."))
original_flags_count = 0
CUSTOM_DATA_KEY = "cf"


def supports_custom_data_prop_search() -> bool:
    return anki_version >= (2, 1, 64)


def anki_color_for_custom_flag(flag: CustomFlag) -> Dict[str, str]:
    # NOTE: Format changed to dict in 2.1.55: https://github.com/ankitects/anki/commit/0c340c4f741c89bcc80f987ee236d506de6a1ad2
    color = (
        (flag.color_light, flag.color_dark)
        if anki_version < (2, 1, 55)
        else {"light": flag.color_light, "dark": flag.color_dark}
    )
    return cast(Dict[str, str], color)


def load_custom_flags(self: FlagManager) -> None:
    global original_flags_count
    original_flags_count = len(self._flags)
    path = ":/icons/flag.svg" if anki_version < (2, 1, 55) else "icons:flag-variant.svg"
    if hasattr(colors, "FG_DISABLED"):
        color = colors.FG_DISABLED
    else:
        color = colors.DISABLED  # type: ignore[attr-defined] # pylint: disable=no-member
    icon = ColoredIcon(
        path=path,
        color=color,
    )

    for i, flag in enumerate(
        config.flags,
        start=1,
    ):
        color_obj = anki_color_for_custom_flag(flag)
        search_node = (
            SearchNode(parsable_text=f"prop:cdn:{CUSTOM_DATA_KEY}={i}")
            if supports_custom_data_prop_search()
            else None
        )
        self._flags.append(
            Flag(
                original_flags_count + i,
                flag.label,
                icon.with_color(color_obj),
                search_node,
                f"custom_flag_action_{i}",
            )
        )


def rename_flag(self: FlagManager, flag_index: int, new_name: str, _old: Any) -> None:
    if flag_index <= original_flags_count:
        _old(self, flag_index, new_name)
        return
    new_flags = config.flags
    new_flags[flag_index - original_flags_count - 1].label = new_name
    config.flags = new_flags
    self.get_flag(flag_index).label = new_name
    gui_hooks.flag_label_did_change()


def setup_browser_menus(self: Browser) -> None:
    # Make sure flags are loaded
    mw.flags.all()
    for i, flag in enumerate(config.flags, start=1):
        action = QAction(self)
        action.setCheckable(True)
        shortcut = flag.shortcut or f"Ctrl+{i+original_flags_count}"
        action.setShortcut(shortcut)
        setattr(self.form, f"custom_flag_action_{i}", action)
        self.form.menuFlag.addAction(action)


def set_flag_on_current_card(self: Reviewer, desired_flag: int, _old: Any) -> None:
    if desired_flag <= original_flags_count:
        _old(self, desired_flag)
        return
    # Set our custom flag
    if get_card_custom_flag(self.card) + original_flags_count == desired_flag:
        flag = 0
    else:
        flag = desired_flag - original_flags_count
    set_card_custom_flag(self.card, flag)


def set_flag_css_vars(web_content: WebContent, context: Optional[Any]) -> None:
    if not isinstance(context, Reviewer):
        return
    flags = config.flags
    light_colors = [flag.color_light for flag in flags]
    dark_colors = [flag.color_dark for flag in flags]

    def color_list_to_defs(colors: list[str]) -> str:
        return ";\n".join(
            f"--flag-{i}: {c}"
            for i, c in enumerate(colors, start=original_flags_count + 1)
        )

    web_content.body += """
<style>
    :root {
        %(light_colors)s
    }
    :root.night-mode {
        %(dark_colors)s
    }
</style>
""" % {
        "light_colors": color_list_to_defs(light_colors),
        "dark_colors": color_list_to_defs(dark_colors),
    }


def get_card_custom_flag(card: Card) -> int:
    data_prop_name = "data" if hasattr(card, "data") else "custom_data"
    raw_data = getattr(card, data_prop_name)
    card_data = json.loads(raw_data) if raw_data else {}
    return int(card_data.get(CUSTOM_DATA_KEY, 0))


def set_card_custom_flag(card: Card, flag: int, update: bool = True) -> None:
    data_prop_name = "data" if hasattr(card, "data") else "custom_data"
    raw_data = getattr(card, data_prop_name)
    card_data = json.loads(raw_data) if raw_data else {}
    card_data[CUSTOM_DATA_KEY] = flag
    setattr(card, data_prop_name, json.dumps(card_data))
    card.flags = 0
    if update:
        CollectionOp(mw, lambda col: col.update_card(card)).run_in_background()


def update_flag_icon(self: Reviewer, _old: Any) -> None:
    flag = self.card.user_flag()
    if not flag:
        flag = get_card_custom_flag(self.card)
        if flag:
            flag += original_flags_count
    self.web.eval(f"_drawFlag({flag});")


def show_reviewer_contextmenu(self: Reviewer, _old: Any) -> None:
    opts = self._contextMenu()
    flag_opts = opts[0][1]
    current_flag = self.card and self.card.user_flag()
    if not current_flag:
        current_flag = get_card_custom_flag(self.card)
        if current_flag:
            current_flag += original_flags_count
    all_flags = self.mw.flags.all()
    custom_flags = config.flags
    for i, opt in enumerate(flag_opts):
        if i >= original_flags_count:
            opt[1] = custom_flags[i - original_flags_count].shortcut or f"Ctrl+{i+1}"
        opt[-1] = {"checked": all_flags[i].index == current_flag}

    m = QMenu(self.mw)
    self._addMenuItems(m, opts)

    gui_hooks.reviewer_will_show_context_menu(self, m)
    qtMenuShortcutWorkaround(m)
    m.popup(QCursor.pos())


def reviewer_shortcut_keys(
    self: Reviewer,
    _old: Any,
) -> Sequence[Union[Tuple[str, Callable], Tuple[Qt.Key, Callable]]]:
    keys = _old(self)
    first_custom_flag_idx = next(
        (i for i, t in enumerate(keys) if t[0] == f"Ctrl+{original_flags_count+1}"),
        None,
    )
    for i, flag in enumerate(config.flags):
        if flag.shortcut:
            key = list(keys[first_custom_flag_idx + i])
            key[0] = flag.shortcut
            keys[first_custom_flag_idx + i] = tuple(key)
    return keys


def clear_custom_flag(self: Card, flag: int) -> None:
    set_card_custom_flag(self, 0, update=False)


def clear_custom_flags_for_cards(
    self: Collection, flag: int, cids: Sequence[CardId], _old: Any
) -> OpChangesWithCount:
    cards = []
    for cid in cids:
        card = self.get_card(cid)
        set_card_custom_flag(card, 0, update=False)
        cards.append(card)
    target = self.add_custom_undo_entry(self.tr.actions_set_flag())
    self.update_cards(cards)
    changes = _old(self, flag, cids)
    return OpChangesWithCount(
        count=changes.count, changes=self.merge_undo_entries(target)
    )


def set_flag_of_selected_cards(self: Browser, flag: int, _old: Any) -> None:
    if flag <= original_flags_count:
        _old(self, flag)
        return
    if (
        get_card_custom_flag(getattr(self, "current_card", self.card))
        + original_flags_count
        == flag
    ):
        flag = 0
    else:
        flag = flag - original_flags_count

    cards = []
    for cid in self.selected_cards():
        card = mw.col.get_card(cid)
        set_card_custom_flag(card, flag, update=False)
        cards.append(card)
    CollectionOp(
        self,
        lambda col: OpChangesWithCount(
            changes=col.update_cards(cards), count=len(cards)
        ),
    ).success(
        lambda out: tooltip(tr.browsing_cards_updated(count=out.count), parent=self)
    ).run_in_background()


def on_browser_did_fetch_row(
    card_or_note_id: ItemId, is_note: bool, row: CellRow, columns: Sequence[str]
) -> None:
    if not is_note:
        card_or_note_id = cast(CardId, card_or_note_id)
        card = mw.col.get_card(card_or_note_id)
        flag_idx = get_card_custom_flag(card)
        if flag_idx and flag_idx <= len(config.flags):
            flag = config.flags[flag_idx - 1]
            color = anki_color_for_custom_flag(flag)
            color = adjusted_bg_color(color)
            row.color = color


def update_flags_menu(self: Browser, _old: Any) -> None:
    flag = self.current_card and self.current_card.user_flag()
    if not flag:
        flag = self.current_card and get_card_custom_flag(self.current_card)
        if flag:
            flag += original_flags_count

    for f in self.mw.flags.all():
        getattr(self.form, f.action).setChecked(flag == f.index)

    qtMenuShortcutWorkaround(self.form.menuFlag)


def after_flag_tree_build(self: SidebarTreeView, root: SidebarItem) -> None:
    if not supports_custom_data_prop_search():
        return
    flag_root = next(
        (
            child
            for child in root.children
            if child.item_type == SidebarItemType.FLAG_ROOT
        ),
        None,
    )
    if not flag_root:
        return

    node = flag_root.search_node
    custom_node = SearchNode(parsable_text=f"prop:cdn:{CUSTOM_DATA_KEY}!=0")
    flag_root.search_node = mw.col.group_searches(node, custom_node, joiner="OR")

    # "No Flag" cannot be properly modified yet due to limitations in custom data property search

    # FLAG_NONE was added in 2.1.50
    # if "FLAG_NONE" in [e.name for e in list(SidebarItemType)]:
    #     flag_none_item = next(
    #         (
    #             child
    #             for child in flag_root.children
    #             if child.item_type == SidebarItemType.FLAG_NONE
    #         ),
    #         None,
    #     )
    # else:
    #     flag_none_item = next(
    #         (
    #             child
    #             for child in flag_root.children
    #             if child.name == tr.browsing_no_flag()
    #         ),
    #         None,
    #     )
    # node = flag_none_item.search_node
    # # `none` is just an example of what's needed to make this work
    # custom_node = SearchNode(parsable_text=f"prop:cdn:{CUSTOM_DATA_KEY}=none")
    # flag_none_item.search_node = mw.col.group_searches(node, custom_node, joiner="AND")


def on_config() -> None:
    dialog = ConfigDialog(mw)
    dialog.open()


def patch() -> None:
    FlagManager._load_flags = wrap(FlagManager._load_flags, load_custom_flags, "after")  # type: ignore[method-assign]
    FlagManager.rename_flag = wrap(FlagManager.rename_flag, rename_flag, "around")  # type: ignore[method-assign]
    Browser.setupMenus = wrap(Browser.setupMenus, setup_browser_menus, "before")  # type: ignore[method-assign]
    Reviewer.set_flag_on_current_card = wrap(  # type: ignore[method-assign]
        Reviewer.set_flag_on_current_card, set_flag_on_current_card, "around"
    )
    Reviewer._update_flag_icon = wrap(  # type: ignore[method-assign]
        Reviewer._update_flag_icon, update_flag_icon, "around"
    )
    Reviewer.showContextMenu = wrap(  # type: ignore[method-assign]
        Reviewer.showContextMenu, show_reviewer_contextmenu, "around"
    )
    Reviewer._shortcutKeys = wrap(  # type: ignore[method-assign]
        Reviewer._shortcutKeys, reviewer_shortcut_keys, "around"
    )
    Card.set_user_flag = wrap(Card.set_user_flag, clear_custom_flag, "after")  # type: ignore[method-assign]
    Collection.set_user_flag_for_cards = wrap(  # type: ignore[method-assign]
        Collection.set_user_flag_for_cards, clear_custom_flags_for_cards, "around"
    )
    Browser.set_flag_of_selected_cards = wrap(  # type: ignore[method-assign]
        Browser.set_flag_of_selected_cards, set_flag_of_selected_cards, "around"
    )
    Browser._update_flags_menu = wrap(  # type: ignore[method-assign]
        Browser._update_flags_menu, update_flags_menu, "around"
    )
    SidebarTreeView._flags_tree = wrap(  # type: ignore[method-assign]
        SidebarTreeView._flags_tree, after_flag_tree_build, "after"
    )


def register_hooks() -> None:
    gui_hooks.webview_will_set_content.append(set_flag_css_vars)
    gui_hooks.browser_did_fetch_row.append(on_browser_did_fetch_row)
    mw.addonManager.setConfigAction(__name__, on_config)


patch()
register_hooks()
