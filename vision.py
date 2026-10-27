"""Experimental estimate of the green progress bar in the game client."""


def progress_percent(image):
    """Estimate progress from a screenshot, or None if the bar is not visible.

    The standard HUD bar occupies approximately x=32–68%, y=1–4% of the
    game view. This deliberately rejects weak signals instead of guessing.
    """
    image = image.convert('RGB')
    w, h = image.size
    left, right = round(w * .322), round(w * .678)
    top, bottom = round(h * .012), max(round(h * .035), round(h * .012) + 1)
    if right <= left or w < 300 or h < 150:
        return None
    pix = image.load()
    green = []
    for x in range(left, right):
        count = 0
        for y in range(top, min(bottom, h)):
            r, g, b = pix[x, y]
            if g > 110 and g > r * 1.35 and g > b * 1.15:
                count += 1
        if count >= max(2, (bottom - top) // 5):
            green.append(x)
    # Progress begins at the left edge; ignore unrelated green pixels.
    if not green or green[0] > left + (right - left) * .05:
        return None
    end = green[0]
    for x in green[1:]:
        if x - end > max(3, (right - left) // 100):
            break
        end = x
    return max(0., min(100., 100 * (end - left + 1) / (right - left)))
