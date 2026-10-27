"""A small, deterministic Geometry Dash-inspired environment for NEAT."""
import argparse
import os
import random
from dataclasses import dataclass
from pathlib import Path

import neat
import pygame

WIDTH, HEIGHT = 1000, 540
GROUND = 420
SIZE = 30
SPEED = 4.0
GRAVITY = 0.65
JUMP = -12.0
FINISH = 2600
# Grouped spike rectangles are conservative hitboxes, not the original game's.
OBJECTS = [
    ('spike', pygame.Rect(400, GROUND - 30, 30, 30)),
    ('spike', pygame.Rect(650, GROUND - 30, 60, 30)),
    ('block', pygame.Rect(940, GROUND - 30, 60, 30)),
    ('spike', pygame.Rect(1250, GROUND - 30, 90, 30)),
    ('block', pygame.Rect(1590, GROUND - 45, 70, 45)),
    ('spike', pygame.Rect(1900, GROUND - 30, 60, 30)),
    ('spike', pygame.Rect(2200, GROUND - 30, 30, 30)),
]


@dataclass
class GeometryDashEnv:
    x: float = 40.0
    y: float = GROUND - SIZE
    vy: float = 0.0
    grounded: bool = True
    alive: bool = True
    won: bool = False
    frames: int = 0

    @property
    def rect(self):
        return pygame.Rect(round(self.x), round(self.y), SIZE, SIZE)

    def inputs(self):
        ahead = [rect for _, rect in OBJECTS if rect.right > self.x + SIZE]
        if not ahead:
            return (self.vy / 15.0, float(self.grounded), 1.0, 0.0, 0.0)
        obj = min(ahead, key=lambda r: r.left)
        # Distances and dimensions are normalised to keep NEAT inputs bounded.
        return (max(-1.0, min(1.0, self.vy / 15.0)), float(self.grounded),
                max(-1.0, min(1.0, (obj.left - (self.x + SIZE)) / 500.0)),
                (GROUND - obj.top) / 150.0, obj.width / 150.0)

    def step(self, jump):
        if not self.alive:
            return
        previous = self.rect
        if jump and self.grounded:
            self.vy = JUMP
            self.grounded = False
        self.x += SPEED
        self.vy += GRAVITY
        self.y += self.vy
        self.frames += 1
        self.grounded = False
        if self.y + SIZE >= GROUND:
            self.y = GROUND - SIZE
            self.vy = 0.0
            self.grounded = True
        for kind, obj in OBJECTS:
            current = self.rect
            if not current.colliderect(obj):
                continue
            if kind == 'block' and self.vy >= 0 and previous.bottom <= obj.top:
                self.y = obj.top - SIZE
                self.vy = 0.0
                self.grounded = True
            else:
                self.alive = False
                return
        if self.x + SIZE >= FINISH:
            self.won = True
            self.alive = False


def fitness(env):
    # Each surviving frame earns one point. Penalise death by the remaining
    # fraction of the level; successful runs get a separate completion bonus.
    return env.frames + (500 if env.won else -20 * max(0, FINISH - env.x) / FINISH)


class Trainer:
    def __init__(self, display, speed):
        self.display = display
        self.speed = speed
        self.generation = 0
        self.screen = None
        self.clock = None
        self.font = None
        if display:
            pygame.init()
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('GD Simulator — NEAT')
            self.clock = pygame.time.Clock()
            self.font = pygame.font.Font(None, 28)

    def evaluate(self, genomes, config):
        self.generation += 1
        agents = [(genome, neat.nn.FeedForwardNetwork.create(genome, config), GeometryDashEnv())
                  for _, genome in genomes]
        for genome, _, _ in agents:
            genome.fitness = 0.0
        max_steps = int(FINISH / SPEED) + 50
        for _ in range(max_steps):
            if self.display:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise KeyboardInterrupt
            active = [a for a in agents if a[2].alive]
            if not active:
                break
            for genome, network, env in active:
                env.step(network.activate(env.inputs())[0] > 0.5)
                genome.fitness = fitness(env)
            if self.display:
                self.draw(agents)
                self.clock.tick(self.speed)
        print(f'Generation {self.generation}: best distance {max(e.x for _, _, e in agents):.0f}/{FINISH}; '
              f'completed {sum(e.won for _, _, e in agents)}/{len(agents)}', flush=True)

    def draw(self, agents):
        self.screen.fill((25, 34, 105))
        lead = max((e.x for _, _, e in agents), default=0)
        offset = max(0, lead - 260)
        pygame.draw.rect(self.screen, (32, 49, 98), (0, GROUND, WIDTH, HEIGHT - GROUND))
        pygame.draw.line(self.screen, (150, 210, 255), (0, GROUND), (WIDTH, GROUND), 2)
        for kind, obj in OBJECTS:
            r = obj.move(-round(offset), 0)
            if kind == 'block':
                pygame.draw.rect(self.screen, (90, 210, 250), r, 2)
            else:
                for x in range(r.left, r.right, 30):
                    pygame.draw.polygon(self.screen, (255, 225, 225), [(x, r.bottom), (x + 15, r.top), (x + 30, r.bottom)], 2)
        for _, _, env in agents:
            if env.alive:
                pygame.draw.rect(self.screen, (70, 235, 145), env.rect.move(-round(offset), 0), 2)
        text = f'Generation {self.generation}   Alive {sum(e.alive for _, _, e in agents)}   Progress {min(100, 100 * lead / FINISH):.0f}%'
        self.screen.blit(self.font.render(text, True, (255, 255, 255)), (16, 16))
        pygame.display.flip()


def main():
    parser = argparse.ArgumentParser(description='Train NEAT in a simplified Geometry Dash-inspired simulation.')
    parser.add_argument('--generations', type=int, default=50)
    parser.add_argument('--speed', type=int, default=120, help='maximum simulation frames per second')
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--headless', action='store_true', help='train without a window')
    args = parser.parse_args()
    if args.generations < 1 or args.speed < 1:
        parser.error('generations and speed must be positive')
    if args.seed is not None:
        random.seed(args.seed)
    config_path = Path(__file__).with_name('config-feedforward.txt')
    config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                         neat.DefaultStagnation, str(config_path))
    population = neat.Population(config)
    population.add_reporter(neat.StdOutReporter(True))
    trainer = Trainer(not args.headless, args.speed)
    try:
        winner = population.run(trainer.evaluate, args.generations)
        print(f'Best fitness: {winner.fitness:.2f}')
    except KeyboardInterrupt:
        print('\nTraining stopped.')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
