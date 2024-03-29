import numpy as np
import time

from data_transformer import DataTransformer
from mountain_car_with_data_collection import MountainCarWithResetEnv
from radial_basis_function_extractor import RadialBasisFunctionExtractor

def moving_average(x, w):
    return np.convolve(x, np.ones(w), 'valid') / w

def evaluate_criterion(env, solver):
    num_of_states = 10
    test_gains = [run_episode(env, solver, is_train=False, epsilon=None)[0] for _ in range(num_of_states)]
    successes = test_gains[test_gains != -200]
    SR = np.sum(successes) / num_of_states
    mean_test_gain = np.mean(test_gains)
    return mean_test_gain, SR

class Solver:
    def __init__(self, number_of_kernels_per_dim, number_of_actions, gamma, learning_rate):
        # Set max value for normalization of inputs
        self._max_normal = 1
        # get state \action information
        self.data_transformer = DataTransformer()
        state_mean = [-3.00283763e-01,  5.61618575e-05]
        state_std = [0.51981243, 0.04024895]
        self.data_transformer.set(state_mean, state_std)
        self._actions = number_of_actions
        # create RBF features:
        self.feature_extractor = RadialBasisFunctionExtractor(number_of_kernels_per_dim)
        self.number_of_features = self.feature_extractor.get_number_of_features()
        # the weights of the q learner
        self.theta = np.random.uniform(-0.001, 0, size=number_of_actions * self.number_of_features)
        # discount factor for the solver
        self.gamma = gamma
        self.learning_rate = learning_rate

    def _normalize_state(self, s):
        return self.data_transformer.transform_states(np.array([s]))[0]

    def get_features(self, state):
        normalized_state = self._normalize_state(state)
        features = self.feature_extractor.encode_states_with_radial_basis_functions([normalized_state])[0]
        return features

    def get_q_val(self, features, action):
        theta_ = self.theta[action*self.number_of_features: (1 + action)*self.number_of_features]
        return np.dot(features, theta_)

    def get_all_q_vals(self, features):
        all_vals = np.zeros(self._actions)
        for a in range(self._actions):
            all_vals[a] = self.get_q_val(features, a)
        return all_vals

    def get_max_action(self, state):
        sparse_features = self.get_features(state)
        q_vals = self.get_all_q_vals(sparse_features)
        return np.argmax(q_vals)

    def get_state_action_features(self, state, action):
        state_features = self.get_features(state)
        all_features = np.zeros(len(state_features) * self._actions)
        all_features[action * len(state_features): (1 + action) * len(state_features)] = state_features
        return all_features

    def update_theta(self, state, action, reward, next_state, done):
        # compute the new weights and set in self.theta. also return the bellman error (for tracking).
        alpha = self.learning_rate
        phi_s = self.get_features(state)
        phi_s_prime = self.get_features(next_state)
        Q_s_a = self.get_q_val(phi_s, action)
        # a_prime = self.get_max_action(next_state)
        # phi_s_prime_a_prime = self.get_state_action_features(next_state, a_prime)
        phi_s_a = self.get_state_action_features(state, action)
        if done:
            Q_s_a_estimated = reward  # done means s_prime is terminal state thus Q=100
        else:
            a_prime = self.get_max_action(next_state)
            Q_s_a_estimated = reward + self.gamma * self.get_q_val(phi_s_prime, a_prime)
        bellman_error = Q_s_a_estimated - Q_s_a
        gradient = phi_s_a
        theta = self.theta + alpha * bellman_error * gradient
        self.theta = theta
        return bellman_error


def modify_reward(reward):
    reward -= 1
    if reward == 0:
        reward = 100.
    return reward


def run_episode(env, solver, is_train=True, epsilon=None, max_steps=200, render=False):
    episode_gain = 0
    deltas = []
    if is_train:
        start_position = np.random.uniform(env.min_position, env.goal_position - 0.01)
        start_velocity = np.random.uniform(-env.max_speed, env.max_speed)
    else:
        start_position = -0.5
        start_velocity = np.random.uniform(-env.max_speed / 100., env.max_speed / 100.)
    state = env.reset_specific(start_position, start_velocity)
    step = 0
    if render:
        env.render()
        time.sleep(0.1)
    while True:
        if epsilon is not None and np.random.uniform() < epsilon:
            action = np.random.choice(env.action_space.n)
        else:
            action = solver.get_max_action(state)
        if render:
            env.render()
            time.sleep(0.1)
        next_state, reward1, done, _ = env.step(action)
        reward = modify_reward(reward1)
        step += 1
        episode_gain += reward
        if is_train:
            deltas.append(solver.update_theta(state, action, reward, next_state, done))
        if done or step == max_steps:
            return episode_gain, np.mean(deltas)
        state = next_state


if __name__ == "__main__":
    env = MountainCarWithResetEnv()
    # seed = 123
    # seed = 234
    seed = 345
    np.random.seed(seed)
    env.seed(seed)

    gamma = 0.999
    learning_rate = 0.05
    epsilon_current = 0.1
    epsilon_decrease = 1.
    epsilon_min = 0.05

    max_episodes = 100000

    solver = Solver(
        # learning parameters
        gamma=gamma, learning_rate=learning_rate,
        # feature extraction parameters
        number_of_kernels_per_dim=[7, 5],
        # env dependencies (DO NOT CHANGE):
        number_of_actions=env.action_space.n,
    )
    reward_for_plot = []
    SR_for_plot = []
    initial_state_value_for_plot = []
    avg_bellman_err_for_plot = []
    for episode_index in range(1, max_episodes + 1):
        episode_gain, mean_delta = run_episode(env, solver, is_train=True, epsilon=epsilon_current)

        # reduce epsilon if required
        epsilon_current *= epsilon_decrease
        epsilon_current = max(epsilon_current, epsilon_min)

        print(f'after {episode_index}, reward = {episode_gain}, epsilon {epsilon_current}, average error {mean_delta}')
        # evaluation
        # saving data
        reward_for_plot.append(episode_gain)
        s0 = [-0.5, 0]
        phi_s0 = solver.get_features(s0)
        s0_greedy_action = solver.get_max_action(s0)
        initial_state_value_for_plot.append(solver.get_q_val(phi_s0, s0_greedy_action))
        avg_bellman_err_for_plot.append(mean_delta)

        # termination condition:
        if episode_index % 10 == 9:
            test_gains = [run_episode(env, solver, is_train=False, epsilon=0.)[0] for _ in range(10)]
            mean_test_gain = np.mean(test_gains)
            failures = np.sum(test_gains.count(-200))
            successes = 10 - failures
            SR = np.sum(successes) / 10
            SR_for_plot.append(SR)
            print(f'tested 10 episodes: mean gain is {mean_test_gain}')
            if mean_test_gain >= -75.:
                print(f'solved in {episode_index} episodes')
                run_episode(env, solver, is_train=False, render=True)
                break

    Reward = np.array(reward_for_plot)
    SR = np.array(SR_for_plot)
    InitStateV = np.array(initial_state_value_for_plot)
    BellmanErr = np.array(avg_bellman_err_for_plot)
    BellmanErr_avged = moving_average(BellmanErr, 100)
    X1 = range(0, len(InitStateV))
    np.savez('seed345', Reward=Reward, SR=SR, InitStateV=InitStateV, BellmanErr=BellmanErr_avged, X1=X1)
    # np.savez('seed123',InitStateV=InitStateV, BellmanErr=BellmanErr_avged, X1=X1)
    run_episode(env, solver, is_train=False, render=True)
