"""Drive the persistent wall through visible controls without bypassing draft guards."""

MODES = {"Images": "content", "Content": "content", "Arrange": "arrange", "Test": "test",
         "Test colour": "test", "Arrange tablet": "arrange", "Saved arrangements": "arrange", "Saved content": "content"}


def mode_button(page, mode):
    return page.locator(f'[data-workspace-mode="{mode}"]:visible').first


def tablet_button(page, device=None):
    identity = f'[data-device-id="{device}"]' if device else ""
    return page.locator(f':is(.roster-pick,.dev-pick){identity}:visible')


def clear_selection(page):
    back = page.locator("#tablet-back")
    if back.is_visible():
        back.click()


def task(page, name, keyboard=False):
    drawer = page.locator("#server-drawer")
    if name == "Server":
        if not drawer.is_visible():
            page.locator("#btn-server").click()
        from playwright.sync_api import expect
        expect(drawer).to_be_visible()
        return
    if drawer.is_visible():
        page.locator("#server-close").click()
    if name == "Measure":
        from playwright.sync_api import expect
        expect(page.locator("#device-sheet")).to_be_visible()
        return
    if name == "Tablets":
        nav = page.locator("#nav-tablets")
        if nav.is_visible() and nav.get_attribute("aria-pressed") != "true":
            nav.click()
        return
    mode = MODES[name]
    if name not in ("Test colour", "Arrange tablet"):
        clear_selection(page)
    control = mode_button(page, mode)
    if name == "Arrange tablet" and page.locator("body").get_attribute("data-mode") == mode:
        return
    if keyboard:
        control.focus()
        control.press("Enter")
    else:
        control.click()
    if name in ("Saved arrangements", "Saved content"):
        refresh = "#btn-layouts-refresh" if name == "Saved arrangements" else "#btn-scenes-refresh"
        page.locator(refresh).click()


OWNERS = {"server-drawer": "Server", "panel-content": "Content", "panel-show": "Arrange", "panel-test": "Test",
          "panel-tablets": "Tablets"}


def reveal(page, locator):
    """Open the mode or drawer that owns a control, as an operator would."""
    owner = locator.first.evaluate("e=>e.closest('#server-drawer,.inspector-pane')?.id||null")
    if owner in OWNERS and not page.locator("#" + owner).is_visible():
        task(page, OWNERS[owner])


def pick(page, device):
    button = tablet_button(page, device)
    if button.get_attribute("aria-pressed") != "true":
        button.click()
    from playwright.sync_api import expect
    expect(page.locator("#device-sheet")).to_be_visible()


def select_tablet(button):
    if button.get_attribute("aria-pressed") != "true":
        button.click()
