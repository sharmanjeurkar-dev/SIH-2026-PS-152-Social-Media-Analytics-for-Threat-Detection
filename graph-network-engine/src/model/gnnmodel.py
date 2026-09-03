import logging

import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


# ==========================================
# 1. GraphSAGE Neural Network Architecture
# ==========================================
class ThreatGraphSAGE(torch.nn.Module):
    def __init__(self, in_channels: int, hidden_channels: int, out_channels: int):
        super(ThreatGraphSAGE, self).__init__()
        # SAGEConv aggregates features from a node's local neighborhood
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        # 1-hop neighborhood aggregation
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.3, training=self.training)

        # 2-hop neighborhood aggregation
        x = self.conv2(x, edge_index)
        # Log-Softmax for classification probabilities
        return F.log_softmax(x, dim=1)
