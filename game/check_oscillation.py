"""
SPATHODEA R4 FASTLAB — Oscillation Check Utility (Phase 2F Part 3C)
Utility script to verify oscillation detection on recorded trajectories.
"""

import sys
sys.path.insert(0, 'C:/projects/spathodea-r4-fastlab')
from game.oscillation_detector import analyze_trajectory


def main():
    # Episode A: SIMPLE trajectory
    # A1 -> A2 -> A3 -> A4 -> A5 -> A4 -> A5 -> B5 -> C5 -> D5 -> E5
    positions_a = ['A1', 'A2', 'A3', 'A4', 'A5', 'A4', 'A5', 'B5', 'C5', 'D5', 'E5']
    actions_a = ['DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'DOWN', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT']
    r_a = analyze_trajectory(positions_a, actions_a)

    # Episode B: WALL_DETOUR trajectory (same pattern)
    positions_b = ['A1', 'A2', 'A3', 'A4', 'A5', 'A4', 'A5', 'B5', 'C5', 'D5', 'E5']
    actions_b = ['DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'DOWN', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT']
    r_b = analyze_trajectory(positions_b, actions_b)

    # Episode C: REWARD_HAZARD trajectory (same pattern)
    positions_c = ['A1', 'A2', 'A3', 'A4', 'A5', 'A4', 'A5', 'B5', 'C5', 'D5', 'E5']
    actions_c = ['DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'DOWN', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT']
    r_c = analyze_trajectory(positions_c, actions_c)

    # Print results
    print("Episode A (SIMPLE):")
    print("  Events: %d" % r_a['total_events'])
    print("  Repeated loops: %d" % r_a['repeated_loop_count'])
    for e in r_a['events']:
        print("    Turn %d: %s" % (e['turn'], e['reason']))

    print("\nEpisode B (WALL_DETOUR):")
    print("  Events: %d" % r_b['total_events'])
    print("  Repeated loops: %d" % r_b['repeated_loop_count'])

    print("\nEpisode C (REWARD_HAZARD):")
    print("  Events: %d" % r_c['total_events'])
    print("  Repeated loops: %d" % r_c['repeated_loop_count'])

    # Aggregate
    total_events = r_a['total_events'] + r_b['total_events'] + r_c['total_events']
    total_loops = r_a['repeated_loop_count'] + r_b['repeated_loop_count'] + r_c['repeated_loop_count']

    print("\n" + "=" * 50)
    print("AGGREGATE:")
    print("  Total events: %d" % total_events)
    print("  Total repeated loops: %d" % total_loops)


if __name__ == "__main__":
    main()
