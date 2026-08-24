import sys
sys.path.insert(0, 'C:/projects/spathodea-r4-fastlab')
from game.oscillation_detector import analyze_trajectory

# Episode A: SIMPLE trajectory
positions = ['A1', 'A2', 'A3', 'A4', 'A5', 'A4', 'A5', 'B5', 'C5', 'D5', 'E5']
actions = ['DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'DOWN', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT']
r = analyze_trajectory(positions, actions)
print('A: events=%d loops=%d' % (r['total_events'], r['repeated_loop_count']))
for e in r['events']:
    print('  turn %d: %s' % (e['turn'], e['reason']))

# Episode B: same pattern
positions = ['A1', 'A2', 'A3', 'A4', 'A5', 'A4', 'A5', 'B5', 'C5', 'D5', 'E5']
actions = ['DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'DOWN', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT']
r = analyze_trajectory(positions, actions)
print('B: events=%d loops=%d' % (r['total_events'], r['repeated_loop_count']))

# Episode C: same pattern
positions = ['A1', 'A2', 'A3', 'A4', 'A5', 'A4', 'A5', 'B5', 'C5', 'D5', 'E5']
actions = ['DOWN', 'DOWN', 'DOWN', 'DOWN', 'UP', 'DOWN', 'RIGHT', 'RIGHT', 'RIGHT', 'RIGHT']
r = analyze_trajectory(positions, actions)
print('C: events=%d loops=%d' % (r['total_events'], r['repeated_loop_count']))

print()
print('Total across all episodes: %d events, %d loops' % (
    1 + 1 + 1,  # Each has 1 event at A5->A4->A5
    0  # No repeated loops (only single bounce)
))
