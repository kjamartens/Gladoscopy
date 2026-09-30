import diplib as dip
import numpy as np
import matplotlib.pyplot as plt
import time

# Create test image with NumPy
size = 512
x = np.linspace(-5, 5, size)
y = np.linspace(-5, 5, size)
X, Y = np.meshgrid(x, y)
img_np = np.sin(X) * np.cos(Y) + 0.5 * np.sin(2*X + 2*Y)

# Convert to DIPlib image
img_dip = dip.Image(img_np)

# Time NumPy FFT
start = time.time()
fft_np = np.fft.fft2(img_np)
fft_np_shifted = np.fft.fftshift(fft_np)
mag_np = np.abs(fft_np_shifted)
time_np = time.time() - start

# Time DIPlib FFT
start = time.time()
fft_dip = dip.FourierTransform(img_dip)
mag_dip = dip.Abs(fft_dip)
time_dip = time.time() - start

# Convert DIPlib result back to NumPy for plotting
mag_dip_np = np.array(mag_dip)

# Visualize
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

axes[0, 0].imshow(img_np, cmap='gray')
axes[0, 0].set_title('Original Image')

axes[0, 1].imshow(np.log(mag_np + 1), cmap='viridis')
axes[0, 1].set_title(f'NumPy FFT Magnitude (log)\nTime: {time_np*1000:.2f} ms')

axes[1, 0].imshow(np.array(img_dip), cmap='gray')
axes[1, 0].set_title('DIPlib Image')

axes[1, 1].imshow(np.log(mag_dip_np + 1), cmap='viridis')
axes[1, 1].set_title(f'DIPlib FFT Magnitude (log)\nTime: {time_dip*1000:.2f} ms')

plt.tight_layout()
plt.show()

print(f"\nSpeed Comparison ({size}x{size} image):")
print(f"NumPy FFT:  {time_np*1000:.2f} ms")
print(f"DIPlib FFT: {time_dip*1000:.2f} ms")
print(f"Speedup: {time_np/time_dip:.2f}x")