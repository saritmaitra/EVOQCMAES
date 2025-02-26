# -*- coding: utf-8 -*-
"""Performance analysis.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1Csd0fJi95ozLK8T7BeeIkow5amTh5S0j
"""

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import random, logging
from collections import deque
import tensorflow as tf
from tensorflow.keras import layers
from scipy.optimize import differential_evolution
import random
from tensorflow import keras
import gym
from matplotlib import pyplot as plt
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']

np.random.seed(42)
random.seed(42)
tf.random.set_seed(42)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CONFIG = {
    "mutation_strategies": ['best1bin', 'rand1bin', 'rand2bin', 'currenttobest1bin', 'best1exp', 'rand1exp'],
    "crossover_strategies": ['bin', 'exp'],
    "cma_step_size": 0.3,
    "egt_max_size": 50,
    "dqn_learning_rate": 0.001,
    "max_generations": 100,
    "num_runs": 10,
    "bounds": [(-5, 5), (-5, 5)]
    }

# CMA-ES Implementation
class CMA:
    def __init__(self, dim, step_size=0.3):
        self.dim = dim
        self.mean = np.zeros(dim)
        self.cov_matrix = np.eye(dim)
        self.step_size = step_size

    def sample_population(self, size):
        try:
            return np.random.multivariate_normal(self.mean, self.cov_matrix * self.step_size, size)
        except np.linalg.LinAlgError:
            self.cov_matrix = np.eye(self.dim)
            self.step_size = 0.3
            return np.random.multivariate_normal(self.mean, self.cov_matrix * self.step_size, size)

    def update_covariance(self, population, fitness):
        fitness = np.asarray(fitness)
        if np.max(fitness) - np.min(fitness) == 0:
            return

        fitness = (fitness - np.min(fitness)) / (np.max(fitness) - np.min(fitness) + 1e-10)
        weights = np.exp(-fitness) / np.sum(np.exp(-fitness))

        if weights.ndim == 0:
            weights = np.array([weights])

        weighted_mean = np.sum(weights[:, None] * population, axis=0)
        centered_population = population - weighted_mean
        self.cov_matrix = np.cov(centered_population.T, aweights=weights)
        self.step_size *= np.exp(0.2 * (np.mean(fitness) - 1))

        if not np.all(np.linalg.eigvals(self.cov_matrix) > 0):
            self.cov_matrix = np.eye(self.dim)

# EGT-based Memory Archive
class EGTMemory:
    def __init__(self, max_size=50):
        self.solutions = []
        self.fitness = []
        self.max_size = max_size

    def add_solution(self, solution, fitness):
        if len(self.solutions) < self.max_size:
            self.solutions.append(solution)
            self.fitness.append(fitness)
        else:
            worst_idx = np.argmax(self.fitness)
            if fitness < self.fitness[worst_idx]:
                self.solutions[worst_idx] = solution
                self.fitness[worst_idx] = fitness

    def extract_patterns(self):
        return np.mean(self.solutions, axis=0) if self.solutions else None

# DQN Agent for Adaptive Strategy Selection
class DQNAgent:
    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=2000)
        self.gamma = 0.95
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        self.model = self._build_model()

    def _build_model(self):
        model = tf.keras.Sequential([
            tf.keras.layers.Input(shape=(self.state_size,)),
            tf.keras.layers.Dense(24, activation='relu'),
            tf.keras.layers.Dense(24, activation='relu'),
            tf.keras.layers.Dense(self.action_size, activation='linear')])
        model.compile(loss='mse', optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate))
        return model

    def select_action(self, state):
        state = np.array(state).reshape(1, -1)
        if np.random.rand() <= self.epsilon:
            return np.random.choice(self.action_size)
        q_values = self.model.predict(state, verbose=0)
        return np.argmax(q_values[0])

    def train(self, batch_size=32):
        if len(self.memory) < batch_size:
            return
        batch = random.sample(self.memory, batch_size)
        for state, action, reward, next_state in batch:
            target = reward + self.gamma * np.max(self.model.predict(np.array(next_state).reshape(1, -1), verbose=0))
            target_f = self.model.predict(np.array(state).reshape(1, -1), verbose=0)
            target_f[0][action] = target
            self.model.fit(np.array(state).reshape(1, -1), target_f, epochs=1, verbose=0)
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

class AdaptiveEA:
    def __init__(self, objective_function, bounds, generations=50, num_runs=10):
        self.bounds = bounds
        self.objective_function = objective_function
        self.generations = generations
        self.num_runs = num_runs
        self.agent = DQNAgent(state_size=1, action_size=len(CONFIG["mutation_strategies"]))
        self.egt_memory = EGTMemory()

    def evolve(self):
        all_runs_fitness_history = []  # To store fitness for all runs
        for _ in range(self.num_runs):
            best_solution, best_fitness, fitness_history = self._evolve_single_run()  # Call a helper function for a single run
            all_runs_fitness_history.append(fitness_history)  # Append fitness of this run
        return best_solution, best_fitness, np.mean(all_runs_fitness_history), np.max(all_runs_fitness_history), np.std(all_runs_fitness_history), all_runs_fitness_history
        # Returns: best_solution, best_fitness, mean_fitness, worst_fitness, std_fitness, all_runs_fitness_history

    def _evolve_single_run(self):
        best_solution, best_fitness = None, float('inf')
        fitness_history = []  # Initialize a list to store fitness values
        strategies = CONFIG["mutation_strategies"]

        for generation in range(self.generations):
            strategy_idx = self.agent.select_action([generation])
            mutation_strategy = strategies[strategy_idx]

            result = differential_evolution(
                self.objective_function,
                bounds=self.bounds,
                strategy=mutation_strategy,
                recombination=0.7,
                popsize=20,
                tol=0.01,
                maxiter=1,
                disp=False)

            if result.fun < best_fitness:
                best_fitness = result.fun
                best_solution = result.x

            self.egt_memory.add_solution(result.x, result.fun)
            fitness_history.append(result.fun)

            reward = -result.fun
            next_state = [generation + 1]
            self.agent.memory.append(([generation], strategy_idx, reward, next_state))
            self.agent.train()
        return best_solution, best_fitness, fitness_history  # Return results of a single run

# Objective Functions
def sphere_function(x):
    return np.sum(np.square(x))

def sinusoidal_function(x):
    return np.sin(5 * np.pi * x[0]) * np.sin(5 * np.pi * x[1]) + np.sum(np.square(x))

convex_fitness_history_all_runs = AdaptiveEA(sphere_function, CONFIG["bounds"], CONFIG["max_generations"], CONFIG["num_runs"])
non_convex_fitness_history_all_runs = AdaptiveEA(sinusoidal_function, CONFIG["bounds"], CONFIG["max_generations"], CONFIG["num_runs"])

def compute_metrics(fitness_history_all_runs):
    _, _, _, _, fitness_history = fitness_history_all_runs.evolve()
    best_fitness_per_run = np.min(fitness_history, axis=0)
    avg_fitness_per_generation = np.mean(fitness_history)
    std_fitness_per_generation = np.std(fitness_history)

    best_fitness = np.min(best_fitness_per_run)
    threshold = best_fitness + 0.1 * (np.max(best_fitness_per_run) - best_fitness)
    convergence_generations = np.argmax(fitness_history <= threshold) if np.any(fitness_history <= threshold) else len(fitness_history)
    avg_convergence_generation = convergence_generations

    print("==== Optimization Metrics ====")
    print(f"Best Fitness Value: {best_fitness:.6f}")
    print(f"Mean Best Fitness Across Runs: {np.mean(best_fitness_per_run):.6f}")
    print(f"Standard Deviation of Fitness: {np.std(best_fitness_per_run):.6f}")
    print(f"Average Convergence Generation: {avg_convergence_generation:.2f}")

    return avg_fitness_per_generation, std_fitness_per_generation

print("\nConvex Function (Sphere Function) Metrics")
convex_avg_fitness, convex_std_fitness = compute_metrics(convex_fitness_history_all_runs)
print("\nNon-Convex Function (Sinusoidal Function) Metrics")
non_convex_avg_fitness, non_convex_std_fitness = compute_metrics(non_convex_fitness_history_all_runs)

from collections import defaultdict

functions = {
    "sphere": sphere_function,
    "sinusoidal": sinusoidal_function,}

for function_name, function in functions.items():
    print(f"\nEvaluating {function_name} function:")
    metrics = defaultdict(list)

    for strategy in CONFIG["mutation_strategies"]:
        best_fitness_all_runs = []
        convergence_speeds = []
        quality_measures = []

        for run in range(CONFIG["num_runs"]):
            result = differential_evolution(
                function,
                CONFIG["bounds"],
                strategy=strategy,
                maxiter=CONFIG["max_generations"])
            best_fitness_all_runs.append(result.fun)

            conv_speed = next(
                (i for i, val in enumerate(result.x) if val <= 1.05 * result.fun),
                CONFIG["max_generations"])
            convergence_speeds.append(conv_speed)

            quality_measures.append(np.std(result.x))

        metrics['strategy'].append(strategy)
        metrics['AOV'].append(np.mean(best_fitness_all_runs))
        metrics['C_s'].append(np.mean(convergence_speeds))
        metrics['Q_measure'].append(np.mean(quality_measures))

    metrics['AOV Rank'] = np.argsort(np.argsort(metrics['AOV']))
    metrics['C_s Rank'] = np.argsort(np.argsort(metrics['C_s']))
    metrics['Q_measure Rank'] = np.argsort(np.argsort(metrics['Q_measure']))
    metrics['Average Rank'] = (
        metrics['AOV Rank'] + metrics['C_s Rank'] + metrics['Q_measure Rank']) / 3

    for i in range(len(CONFIG["mutation_strategies"])):
        print(
            f"Strategy: {metrics['strategy'][i]}, "
            f"AOV: {metrics['AOV'][i]:.4f}, "
            f"C_s: {metrics['C_s'][i]:.2f}, "
            f"Q_measure: {metrics['Q_measure'][i]:.4f}, "
            f"Avg Rank: {metrics['Average Rank'][i]:.2f}")