import pygame

# --- Game Constants ---
BUFFER_SIZE = 4096
TARGET_COVERAGE = 0.50  # Minimum coverage required to claim a square (50%)

# --- Screen Constants ---
GRID_AREA_SIZE = 480  # 
GRID_TOP_LEFT = (50, 70)  # Top-left corner of the grid on screen
SCREEN_WIDTH = GRID_TOP_LEFT[0] + GRID_AREA_SIZE + 200  # Add 100 pixels for the player list
SCREEN_HEIGHT = GRID_TOP_LEFT[1] + GRID_AREA_SIZE + 50  # Add 50 pixels for the player list

# --- Colors for the game ---
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_LIGHT_GREY = (211, 211, 211)
COLOR_DARK_GREY = (100, 100, 100)
COLOR_GRID_LINE = (180, 180, 180)
COLOR_SCRIBBLE = (50, 50, 50) 
COLOR_INPUT_BG = (240, 240, 240)
COLOR_INPUT_BORDER = (150, 150, 150)
COLOR_INPUT_BORDER_ACTIVE = (0, 120, 215)
COLOR_BUTTON = (0, 120, 215)
COLOR_BUTTON_TEXT = COLOR_WHITE
COLOR_STATUS_INFO = (50, 50, 150)
COLOR_STATUS_ERROR = (180, 50, 50)
COLOR_STATUS_SUCCESS = (50, 150, 50)

# --- Alpha Values ---
ALPHA_LOCK_SELF = 100
ALPHA_LOCK_OTHER = 100

# helper function for drawing rects 
def draw_rect_alpha(surface, color_rgb, alpha, rect):
    """ Draw a rectangle with alpha transparency onto a surface. 
        To allow player to scribble and see the trail."""

    shape_surf = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, color_rgb + (alpha,), shape_surf.get_rect())
    surface.blit(shape_surf, rect)