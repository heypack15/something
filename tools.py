def navigate(url: str):
    """Navigate to a specific URL. Use this to start or change sites.

    Args:
        url: The URL to navigate to (e.g., google.com).
    """
    pass

def click(element_id: int):
    """Click on an interactive element identified by its numeric ID from the accessibility tree/screenshot.

    Args:
        element_id: The unique ID of the element to click.
    """
    pass

def type_text(element_id: int, text: str, press_enter: bool = True):
    """Type text into an input field identified by its numeric ID.

    Args:
        element_id: The ID of the input element.
        text: The text to type.
        press_enter: Whether to press Enter after typing. Defaults to True.
    """
    pass

def finish():
    """Call this when the objective is achieved or if it is impossible to continue."""
    pass