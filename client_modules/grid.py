import pygame
from .constants import *


class GridComponent:
    """ Grid class for drawing and interacting with the game grid. 
        Handles mouse events for scribbling and locking squares."""
    def __init__(self, game_client):
        """Initialize grid component for drawing and interacting with game grid"""
        self.client = game_client
        self.scribble_points = []
        self.scribble_coverage_pixels = set()
        self.calculate_square_size()

    def calculate_square_size(self):
        """Calculate sizes of each grid based square based on overall grid size"""
        if self.client.grid_size > 0:
            self.square_pixel_size = GRID_AREA_SIZE / self.client.grid_size
            self.total_pixels_in_square = self.square_pixel_size**2

    def coords_to_grid(self, screen_x, screen_y):
        """Convert screen x, y coordinates to grid row, col
        Returns: Tuple corresponding to grid square or returns None, None if outside of grid"""

        if not (
            GRID_TOP_LEFT[0] <= screen_x < GRID_TOP_LEFT[0] + GRID_AREA_SIZE
            and GRID_TOP_LEFT[1] <= screen_y < GRID_TOP_LEFT[1] + GRID_AREA_SIZE
        ):
            # Click outside grid area
            return None, None

        local_x = screen_x - GRID_TOP_LEFT[0]
        local_y = screen_y - GRID_TOP_LEFT[1]

        col = int(local_x // self.square_pixel_size)
        row = int(local_y // self.square_pixel_size)
        # Make sure coordinates are within grid
        col = max(0, min(col, self.client.grid_size - 1))
        row = max(0, min(row, self.client.grid_size - 1))
        return row, col

    def grid_to_screen_rect(self, r, c):
        """Convert grid row, col to screen Rect. """
        x0 = GRID_TOP_LEFT[0] + c * self.square_pixel_size
        y0 = GRID_TOP_LEFT[1] + r * self.square_pixel_size
        return pygame.Rect(x0, y0, self.square_pixel_size, self.square_pixel_size)

    def draw(self, screen):
        """Draws entire grid including claimed squares, locks, grid lines and scribbles"""

        # Draw grid background border
        grid_bg_rect = pygame.Rect(GRID_TOP_LEFT[0], GRID_TOP_LEFT[1], GRID_AREA_SIZE, GRID_AREA_SIZE)
        pygame.draw.rect(screen, COLOR_DARK_GREY, grid_bg_rect, 1)  # Border

        # Draw filled grid squares
        if self.client.board:
            for r in range(self.client.grid_size):
                for c in range(self.client.grid_size):
                    player_id = self.client.board[r][c]
                    square_rect = self.grid_to_screen_rect(r, c)
                    fill_color = COLOR_WHITE
                    outline_color = COLOR_GRID_LINE

                    if player_id != 0:
                        player_info = self.client.players.get(player_id)
                        if player_info:
                            fill_color = self.client.hex_to_rgb(player_info['color'])
                        else:
                            fill_color = COLOR_DARK_GREY  # Unknown player claimed
                        outline_color = COLOR_BLACK

                    pygame.draw.rect(screen, fill_color, square_rect)
                    if fill_color != COLOR_WHITE:
                        pygame.draw.rect(screen, outline_color, square_rect, 1)

        # Draw Grid Lines
        for i in range(1, self.client.grid_size):
            x = GRID_TOP_LEFT[0] + i * self.square_pixel_size
            pygame.draw.line(screen, COLOR_GRID_LINE, (x, GRID_TOP_LEFT[1]), (x, GRID_TOP_LEFT[1] + GRID_AREA_SIZE))
            y = GRID_TOP_LEFT[1] + i * self.square_pixel_size
            pygame.draw.line(screen, COLOR_GRID_LINE, (GRID_TOP_LEFT[0], y), (GRID_TOP_LEFT[0] + GRID_AREA_SIZE, y))

        # Draw Scribble Lines if scribbling
        if self.client.is_scribbling and len(self.scribble_points) > 1:
            pygame.draw.lines(screen, COLOR_SCRIBBLE, False, self.scribble_points, 3)

        # Draw Lock Indicators
        for (r, c), player_id in self.client.locked_squares.items():
            square_rect = self.grid_to_screen_rect(r, c)
            player_info = self.client.players.get(player_id)
            lock_color_rgb = COLOR_DARK_GREY  # Default if player unknown
            alpha = ALPHA_LOCK_OTHER

            if player_info:
                lock_color_rgb = self.client.hex_to_rgb(player_info['color'])

            if player_id == self.client.my_player_id:
                alpha = ALPHA_LOCK_SELF

            draw_rect_alpha(screen, lock_color_rgb, alpha, square_rect)

    def handle_mouse_down(self, pos):
        """Draws scribble line if scribbling and sends lock request"""
        
        
        if self.client.game_over or not self.client.connected:
            return
        if self.client.is_scribbling:
            return  # Should not happen if logic correct

        r, c = self.coords_to_grid(pos[0], pos[1])
        if r is not None:  # Click was inside grid
            is_white = self.client.board[r][c] == 0
            is_locked = (r, c) in self.client.locked_squares

            if is_white and not is_locked:
                self.client.set_status(f"Requesting lock for ({r},{c})...", COLOR_STATUS_INFO)
                self.client.pending_lock_request = (r, c)
                self.client.send_message(f"LOCK_REQUEST|{r}|{c}\n")
            elif not is_white:
                self.client.set_status(f"Square ({r},{c}) already taken.", COLOR_STATUS_INFO)
            elif is_locked:
                locker_id = self.client.locked_squares.get((r, c))
                locker_name = self.client.players.get(locker_id, {}).get('name', f'P{locker_id}')
                self.client.set_status(f"Square ({r},{c}) locked by {locker_name}.", COLOR_STATUS_INFO)

    def handle_mouse_motion(self, pos):
        """Update scribble points while mouse is being dragged."""

        
        if self.client.is_scribbling and self.client.scribble_square is not None:
            r_curr, c_curr = self.coords_to_grid(pos[0], pos[1])
            if (r_curr, c_curr) == self.client.scribble_square:
                self.scribble_points.append(pos)
                radius = 3  
                #  Calculate coverage pixels
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        px, py = int(pos[0] + dx), int(pos[1] + dy)
                        sq_rect = self.grid_to_screen_rect(
                            self.client.scribble_square[0], self.client.scribble_square[1]
                        )
                        if sq_rect.collidepoint(px, py):
                            self.scribble_coverage_pixels.add((px, py))

    def handle_mouse_up(self):
        """HAndle mouse release events such as claiming or releasing locks."""
        if self.client.is_scribbling and self.client.scribble_square is not None:
            r, c = self.client.scribble_square
            print(f"Released mouse in ({r},{c})")

            coverage = 0
            if self.total_pixels_in_square > 0:
                coverage = len(self.scribble_coverage_pixels) / self.total_pixels_in_square
            self.client.log_message(
                f"Square ({r},{c}): Covered ~{len(self.scribble_coverage_pixels)} pixels, Coverage ~{coverage:.2%}"
            )

            if coverage >= TARGET_COVERAGE:
                self.client.log_message(f"Attempting claim ({r},{c})")
                self.client.send_message(f"CLAIM_ATTEMPT|{r}|{c}\n")
                self.client.set_status(f"Attempting claim for ({r},{c})...", COLOR_STATUS_SUCCESS)
            else:
                self.client.log_message(f"Releasing lock ({r},{c}) - Low coverage")
                self.client.send_message(f"RELEASE_LOCK|{r}|{c}\n")
                self.client.set_status(f"Claim failed for ({r},{c}) - <50% coverage.", COLOR_STATUS_INFO)

            self.reset_scribble_state()

        elif self.client.pending_lock_request:
            print("Mouse released while lock pending.")
            self.client.pending_lock_request = None
            self.client.set_status("Lock request cancelled.", COLOR_STATUS_INFO)

    def reset_scribble_state(self):
        """Resets the scribble-related state."""
        self.client.is_scribbling = False
        self.client.scribble_square = None
        self.scribble_points = []
        self.scribble_coverage_pixels.clear()
