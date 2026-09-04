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
    def __init__(
        self,
        in_channels: int = 8,
        hidden_channels: int = 32,
        out_channels: int = 3,
        dropout: float = 0.3,
    ):
        super(ThreatGraphSAGE, self).__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.bn1 = torch.nn.BatchNorm1d(hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        # 1-hop neighborhood aggregation
        x = self.conv1(x, edge_index)
        if x.size(0) > 1:
            x = self.bn1(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        # 2-hop neighborhood aggregation
        x = self.conv2(x, edge_index)
        # Log-Softmax for classification probabilities
        return F.log_softmax(x, dim=1)
