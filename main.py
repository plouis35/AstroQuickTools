from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label


class HelloWorldApp(App):
    def build(self):
        self.tap_count = 0
        layout = BoxLayout(
            orientation="vertical",
            padding=32,
            spacing=20,
        )

        self.message = Label(
            text="Bonjour Android !",
            font_size="28sp",
        )
        button = Button(
            text="Appuie ici",
            font_size="20sp",
            size_hint=(1, 0.35),
        )
        button.bind(on_press=self.on_button_press)

        layout.add_widget(self.message)
        layout.add_widget(button)
        return layout

    def on_button_press(self, _button):
        self.tap_count += 1
        self.message.text = f"Bonjour Android !\nAppuis : {self.tap_count}"


if __name__ == "__main__":
    HelloWorldApp().run()
