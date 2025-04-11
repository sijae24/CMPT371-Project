import pygame
from .constants import *


class LoginComponent:
    """ Login class for handling user input and connecting to the game server. 
        Handles key presses, mouse clicks, and drawing the login screen."""
    def __init__(self, game_client):
        
        self.client = game_client
        self.setup_input_fields()
        
        # Load the image
        try:
            import os
            image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "draw.png")
            self.logo_image = pygame.image.load(image_path)
            self.logo_image = pygame.transform.scale(self.logo_image, (150, 150)) 
        except pygame.error as e:
            print(f"Error loading image: {e}")
            self.logo_image = None

    def setup_input_fields(self):
        """Initialize input fields for the login screen, including the player name, server ip, and server port fields.
           These fields are used to collect user input and connect to the game server."""

        self.input_fields = {
            "name": {
                "rect": pygame.Rect(SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 60, 300, 30),
                "text": self.client.player_name,
                "label": "Player Name:",
            },
            "ip": {
                "rect": pygame.Rect(SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 20, 300, 30),
                "text": self.client.server_ip,
                "label": "Server IP:",
            },
            "port": {
                "rect": pygame.Rect(SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 + 20, 300, 30),
                "text": self.client.server_port,
                "label": "Server Port:",
            },
        }
        self.connect_button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 70, 200, 40)
        self.active_field = None

    def draw(self, screen):
        """Draw the login screen with title, input fields, connect button, and status message."""
        
        screen.fill(COLOR_WHITE)

        # Draw the logo image if loaded
        if self.logo_image:
            # Position the image above the title
            image_rect = self.logo_image.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 180))
            screen.blit(self.logo_image, image_rect)

        # Center the title
        title_surf = self.client.font_title.render("Deny & Conquer", True, COLOR_BLACK)
        screen.blit(title_surf, (SCREEN_WIDTH // 2 - title_surf.get_width() // 2, SCREEN_HEIGHT // 2 - 120))

        # Draw Input Fields
        for key, field in self.input_fields.items():
            # Draw Label
            label_surf = self.client.font_ui.render(field["label"], True, COLOR_BLACK)
            label_rect = label_surf.get_rect(midright=(field["rect"].left - 10, field["rect"].centery))
            screen.blit(label_surf, label_rect)

            # Draw Input Box
            border_color = COLOR_INPUT_BORDER_ACTIVE if self.active_field == key else COLOR_INPUT_BORDER
            pygame.draw.rect(screen, COLOR_INPUT_BG, field["rect"])
            pygame.draw.rect(screen, border_color, field["rect"], 1)

            # Draw Text Inside Box
            text_surf = self.client.font_ui.render(field["text"], True, COLOR_BLACK)
            text_rect = text_surf.get_rect(midleft=(field["rect"].left + 5, field["rect"].centery))
            screen.blit(text_surf, text_rect)

        # Draw Connect Button
        pygame.draw.rect(screen, COLOR_BUTTON, self.connect_button_rect, border_radius=5)
        btn_text_surf = self.client.font_ui.render("Connect", True, COLOR_BUTTON_TEXT)
        btn_text_rect = btn_text_surf.get_rect(center=self.connect_button_rect.center)
        screen.blit(btn_text_surf, btn_text_rect)

        # Draw Status Message
        status_surf = self.client.font_ui_small.render(self.client.status_text, True, self.client.status_color)
        status_rect = status_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 130))
        screen.blit(status_surf, status_rect)

    def handle_mouse_click(self, pos):
        """Handle mouse click event on the login screen.
        
        If the connect button is clicked, attempt to connect to the game server.
        If an input field is clicked, activate it for user input.
        """

        # Check connect button click
        if self.connect_button_rect.collidepoint(pos):
            self.connect_to_game()
            return

        # Check input fields
        self.active_field = None
        for key, field in self.input_fields.items():
            if field["rect"].collidepoint(pos):
                self.active_field = key
                print(f"Activated field: {key}")
                break

    def handle_key_press(self, event):
        """Handle key press events for the active input field on the login screen."""

        if not self.active_field:
            return


        field = self.input_fields[self.active_field]
        # Handle backspace and return keys
        if event.key == pygame.K_BACKSPACE:
            field["text"] = field["text"][:-1]
        elif event.key == pygame.K_RETURN:
            if self.active_field == "port":  
                self.connect_to_game()
            else:  # Move to next field
                keys = list(self.input_fields.keys())
                try:
                    next_index = keys.index(self.active_field) + 1
                    if next_index < len(keys):
                        self.active_field = keys[next_index]
                    else:
                        self.active_field = None
                except ValueError:
                    self.active_field = None
        elif event.unicode.isprintable():
            field["text"] += event.unicode

    def connect_to_game(self):
        """Update client state with current field values and call client's connect method."""

        self.client.player_name = self.input_fields["name"]["text"]
        self.client.server_ip = self.input_fields["ip"]["text"]
        self.client.server_port = self.input_fields["port"]["text"]
        self.client.connect_to_game()
