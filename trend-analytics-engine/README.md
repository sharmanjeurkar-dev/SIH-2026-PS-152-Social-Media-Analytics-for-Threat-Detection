# Trend Analytics Engine

**SIH 2026 PS:152 - National Technical Research Organisation (NTRO)**  
**Social Media Analytics for Threat Detection: Real-Time Trend & Topic Detection**

The **Trend Analytics Engine** identifies, ranks, and predicts rising trends, viral keywords, and shifting discussions as they emerge chronologically across social media streams. It maintains an active radar of the **Top 200 Trending Hashtags** and synchronizes directly with the Web Scraper (`data-injestion-pieline`) and the Graph Database (`graph-network-engine`).

---

## 1. Mathematical Architecture

### A. Trend Dynamics
1. **Velocity ($\Delta F / \Delta t$)**: Hourly rate of change in hashtag frequency:
   $$\text{Velocity} = \frac{F_{\text{current}} - F_{\text{previous}}}{\Delta t}$$
2. **Acceleration ($\Delta V / \Delta t$)**: Rate of change in velocity, serving as a predictive leading indicator for upcoming viral explosions:
   $$\text{Acceleration} = \frac{\text{Velocity} - V_{\text{previous}}}{\Delta t}$$
3. **Kleinberg Burst Z-Score ($Z$)**: Statistical anomaly detection comparing current window volume against the historical baseline:
   $$Z = \frac{F_{\text{current}} - \mu_{\text{history}}}{\sigma_{\text{history}} + 1.0}$$

### B. Threat-Weighted Surge Index
Fuses velocity, content toxicity, and co-occurrence network connectivity:
$$\text{SurgeScore} = \max(0, \text{Velocity}) \times (1.0 + \text{Toxicity} \times 2.5) \times \log_2(2 + \text{DegreeCentrality})$$

### C. Unified Trend Score (Top 200 Ranking)
Combines surge dynamics, volume, acceleration, and burst deviation to maintain the Top 200 radar:
$$\text{Unified Score} = \text{SurgeScore} \times 0.40 + \min(\text{Volume}, 500) \times 0.25 + \max(0, \text{Acceleration}) \times 0.20 + \max(0, Z) \times 0.15$$

### D. Louvain Community Topic Detection
Hashtags are mapped into an undirected co-occurrence graph ($G_{\text{cooccur}}$). Louvain Community Detection partitions hashtags into dense modular clusters representing cohesive semantic discussion topics.

### E. Narrative Drift & Thematic Shift Detection
Measures Jaccard similarity across sliding chronological windows:
$$J(C_t, C_{t-1}) = \frac{|C_t \cap C_{t-1}|}{|C_t \cup C_{t-1}|}$$
- **$J < 0.20$**: `🆕 [NEW_EMERGING_TOPIC]`
- **$J \ge 0.20$ & $\Delta \text{Tox} \ge 0.15$**: `⚠️ [ESCALATING_HOSTILITY]`
- **$0.20 \le J < 0.50$**: `🔄 [DRIFTING_NARRATIVE]`

---

## 2. Directory Structure

```
trend-analytics-engine/
├── __init__.py                  # Package exports (TrendAndTopicEngine, TrendingHashtagManager)
├── trend_topic_engine.py        # Core mathematical algorithms & Louvain clustering
├── trending_hashtag_manager.py  # Centralized dynamic 200-hashtag radar & scraper query generator
├── train_trend_detector.py      # Chronological historical simulation runner
├── test_trend_engine.py         # Unit & integration test suite
├── requirements.txt             # Dependencies
└── README.md                    # Engine documentation
```

---

## 3. Usage & CLI Execution

### Running Chronological Trend Simulation
```bash
python train_trend_detector.py --sample 25000 --window_hours 4.0
```

### Running Unit Tests
```bash
python -m unittest test_trend_engine.py
```

### Python API Integration
```python
from trend_analytics_engine import TrendAndTopicEngine, get_trending_hashtag_manager

# 1. Initialize Engine
engine = TrendAndTopicEngine(baseline_window_count=5)

# 2. Analyze Micro-Batch or Sliding Window
analysis = engine.analyze_window(events, dt_hours=1.0, top_n=200)

print("Top Rising Trends:", analysis["rising_trends"][:5])
print("Topic Clusters:", analysis["topic_clusters"][:3])

# 3. Access Dynamic 200 Radar
mgr = get_trending_hashtag_manager()
top_200 = mgr.trending_pool
scraper_batches = mgr.get_search_query_batches(cycle_index=0)
```

