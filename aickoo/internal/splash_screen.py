#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Splash Screen Module - Displays a splash screen on program startup
Uses pygame instead of tkinter for better compatibility with portable Python
"""

import logging
import os
import threading
import time
from typing import Optional

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class SplashScreen:
    """A splash screen window that displays during application startup"""
    
    def __init__(self, title="Aickoo AI", duration=3):
        self.title = title
        self.duration = duration
        self._is_running = False
        self._thread = None
        self._screen = None
        self._clock = None
        self._image = None
        self.image_width = 500
        self.image_height = 500
        self._progress = 0
        self._progress_lock = threading.Lock()
    
    def _create_window(self):
        """Create the splash screen window"""
        if not PYGAME_AVAILABLE:
            return
        
        pygame.init()
        screen_info = pygame.display.Info()
        splash_image_path = os.path.join(
            os.getcwd(),
            'web', 'assets', 'aickoo-assistant-splash.png'
        )
        
        try:
            from PIL import Image as PILImage
            pil_image = PILImage.open(splash_image_path).convert('RGBA')
            self.image_width, self.image_height = pil_image.size
            mode = pil_image.mode
            size = pil_image.size
            data = pil_image.tobytes()

            flags = pygame.NOFRAME
            self._screen = pygame.display.set_mode(
                (self.image_width, self.image_height), flags
            )
            pygame.display.set_caption(self.title)
            self._image = pygame.image.fromstring(data, size, mode).convert_alpha()
        except ImportError:
            try:
                self._image = pygame.image.load(splash_image_path).convert_alpha()
                self.image_width, self.image_height = self._image.get_size()
            except Exception as e:
                print(e)
                self._image = None
        except Exception as e:
            print(e)
            self._image = None
        
        x = (screen_info.current_w - self.image_width) // 2
        y = (screen_info.current_h - self.image_height) // 2
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{x},{y}"

        self._clock = pygame.time.Clock()
        self._run_main_loop()
    
    def _run_main_loop(self):
        """Run the pygame main loop"""
        while self._is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._is_running = False
            
            if self._screen:
                self._screen.fill((10, 10, 10))
                
                if self._image:
                    self._screen.blit(self._image, (0, 0))
                
                self._draw_progress_bar()
                
                pygame.display.flip()
            
            self._clock.tick(10)
        
        if self._screen:
            pygame.quit()
    
    def _draw_progress_bar(self):
        """Draw the progress bar on the screen"""
        with self._progress_lock:
            progress = self._progress
        
        progress_bar_height = 4
        progress_bar_margin = 20
        
        bg_rect = (
            progress_bar_margin,
            self.image_height - progress_bar_height - progress_bar_margin,
            self.image_width - progress_bar_margin * 2,
            progress_bar_height
        )
        
        fill_width = int((self.image_width - progress_bar_margin * 2) * (progress / 100))
        fill_rect = (
            progress_bar_margin,
            self.image_height - progress_bar_height - progress_bar_margin,
            fill_width,
            progress_bar_height
        )
        
        pygame.draw.rect(self._screen, (42, 42, 42), bg_rect)
        pygame.draw.rect(self._screen, (39, 174, 96), fill_rect)
    
    def _update_progress(self, progress):
        """Update the progress bar"""
        with self._progress_lock:
            self._progress = max(0, min(100, progress))
    
    def _start_progress_animation(self):
        """Start the progress bar animation"""
        def animate():
            progress = 0
            while self._is_running and progress < 100:
                progress += 3
                self._update_progress(progress)
                time.sleep(0.5)
            if self._is_running:
                self.hide()
        threading.Thread(target=animate, daemon=True).start()
    
    def show(self):
        """Show the splash screen in a separate thread"""
        if not PYGAME_AVAILABLE:
            return
        
        self._is_running = True
        self._thread = threading.Thread(target=self._create_window, daemon=True)
        self._thread.start()
        self._start_progress_animation()
    
    def hide(self):
        """Hide the splash screen"""
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def update_message(self, message):
        """Update the loading message (not implemented in pygame version)"""
        pass


def show_splash(title="Aickoo AI", duration=3) -> Optional[SplashScreen]:
    """Create and show a splash screen"""
    if not PYGAME_AVAILABLE:
        return None
    
    splash = SplashScreen(title, duration)
    splash.show()
    return splash
