import concurrent.futures
import threading
import time
import os
# Define a flag to control the continuous task
stop_continuous_task = False
total_th1 = 0;
total_th2 = 0
# Define a function for continuous execution
def continuous_task():
    global stop_continuous_task, total_th1
    while not stop_continuous_task:
        print("Continuous task running:",total_th1)
        total_th1+=1
        time.sleep(1)


def continuous_task2():
    global stop_continuous_task, total_th2
    while not stop_continuous_task:
        print("Continuous task 2 running:",total_th2)
        total_th2+=1
        time.sleep(.5)

# Define a CPU-bound function
def cpu_bound_task(n):
    result = 0
    for i in range(n):
        result += i
    # print('Cpu-bound task completed')
    return result

def main():
    # Get the number of CPU threads available
    global stop_continuous_task
    # Start the continuous task in a separate thread
    continuous_thread = threading.Thread(target=continuous_task)
    continuous_thread.daemon = True  # Allow the program to exit if only this thread is running
    continuous_thread.start()

    # Start the continuous task in a separate thread
    continuous_thread2 = threading.Thread(target=continuous_task2)
    continuous_thread2.daemon = True  # Allow the program to exit if only this thread is running
    continuous_thread2.start()

    time.sleep(10)
    stop_continuous_task = True
    

if __name__ == "__main__":
    main()
