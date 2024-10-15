import pstats

# Load the profiler data from the file
p = pstats.Stats('profiling_results.prof')

# Sort the data by cumulative time
p.sort_stats('time')
print('------------------------------------------')
print('------------------------------------------')
print('------------------------------------------')
print('------------------------------------------')
print('------------------------------------------')
# Print the data
p.print_stats(100)

