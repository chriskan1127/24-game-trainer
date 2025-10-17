# Details to Fix:

- When the round ends, and we go to round results screen, before the next round starts, we should unfreeze all controls again. Thus, all buttons should be usable prior to next round starting (for example, while we are on round results screen)

- When attempting to fix the Round Results Screen, or any frontend modifications for that matter, make changes in multiplayer.kv file to adjust its frontend properties. That should be the best fix to truly center the screen. If stuck, look at surrounding code in the .kv files for tips on how to achieve this properly. In fact, try to move frontend defining components into the multiplayer.kv file for simplicity and better control. An example would be this portion:
    from kivy.uix.label import Label
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.anchorlayout import AnchorLayout
        from kivy.graphics import Color, Rectangle, RoundedRectangle

        # Clear any existing widgets
        self.clear_widgets()

        # Full screen background
        with self.canvas.before:
            Color(0.05, 0.05, 0.15, 0.95)  # Semi-transparent dark background
            self.full_bg_rect = Rectangle(size=self.size, pos=self.pos)
            self.bind(size=self._update_full_bg, pos=self._update_full_bg)
Remember, you are an expert!

