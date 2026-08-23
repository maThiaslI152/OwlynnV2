---
name: matplotlib_horizontal_bar
category: data
description: Procedural skill synthesized from user workflow
triggers: [matplotlib_horizontal_bar]
version: '1.0'
---
# Matplotlib Horizontal Bar Chart
Use this template for comparing categories with a single metric.

```python
import matplotlib.pyplot
plt.style.use('ggplot')
versions = ['Python 3.12', 'Python 3.13', 'Python 3.14']
times = [1.0, 1.15, 1.3]
crs = plt.barh(versions, times)
colors = ['gray', 'orange', 'red']
for i, c in enumerate(colors): crs[i].set_color(c)
plt.xlabel('Execution Time (x)')
plt.ylabel('Python Version')
plt.title('Performance Comparison Across Versions')
plt.gca().invert_yaxis()  # Latest version at top
fig, ax = plt.subplots()
ax.barh(versions, times)
for i, t in enumerate(times):
    ax.text(t + 0.02, i, f'{t}x')
plt.tight_layout()
plt.savefig('python_benchmarks.png', dpi=300)