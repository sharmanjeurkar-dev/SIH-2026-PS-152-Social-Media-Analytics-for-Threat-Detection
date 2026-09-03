from typing import Dict, Tuple

import networkx as nx
import torch
import torch.nn.functional as F
from model.gnnmodel import ThreatGraphSAGE
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv


class GNNPIPELINE:
    """
    Translates NetworkX graphs into PyTorch Geometric tensors, generates pseudo-labels
    for zero-shot bootstrapping, and executes the GraphSAGE threat classification.
    """

    def __init__(self, hidden_dim: int = 16) -> None:
        self.num_features = (
            5  # In-degree, Out_degree,Amplification_ratio,Toxicity,Pagerank
        )
        self.target_classifiers = 3  # 0:Organic_user 1:Bot 2:Malicious_User]
        self.model = ThreatGraphSAGE(
            in_channels=self.num_features,
            out_channels=self.target_classifiers,
            hidden_channels=hidden_dim,
        )

    def networkx_to_pyg(self, G: nx.DiGraph, centrality_metrics: Dict[str, Dict]):
        """
        Converts the NetworkX DiGraph into a PyG Data object.
        Fuses topological metrics and Member 2's NLP scores into the feature tensor.
        """
        node_mapping = {node: i for i, node in enumerate(G.nodes())}
        reverse_mapping = list(G.nodes())

        x_featurtes = []
        pseudo_labels = []

        for node in G.nodes():
            meta = G.nodes[node]
            cent = centrality_metrics.get(node, {})

            in_deg = float(G.in_degree(node))
            out_deg = float(G.out_degree(node))

            amp_ratio = (in_deg + 1) / (out_deg + 1)
            toxicity = float(meta.get("avg_toxicity", 0.0))
            pagerank = float(cent.get("pagerank", 0.0))

            feat_vector = [
                in_deg / 100.0,
                out_deg / 100.0,
                amp_ratio / 10.0,
                toxicity,
                pagerank * 100.0,
            ]

            x_featurtes.append(feat_vector)

            if amp_ratio < 0.1 and out_deg > 50:
                pseudo_labels.append(
                    1
                )  # BOT (Spamming outwards, nobody interacts back)
            elif toxicity > 0.6 and pagerank > 0.01:
                pseudo_labels.append(2)  # MALICIOUS_ACTOR (Toxic Super Spreader)
            else:
                pseudo_labels.append(0)  # ORGANIC_USER

            x = torch.tensor(x_featurtes, dtype=torch.float)
            y = torch.tensor(pseudo_labels, dtype=torch.long)

            edges = [(node_mapping[u], node_mapping[v]) for u, v in G.edges()]
            if not edges:
                edge_index = torch.empty((2, 0), dtype=torch.long)
            else:
                edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()

            def train_and_predict(self, data: Data, epochs: int = 50) -> torch.Tensor:
                """
                Trains the GraphSAGE model on the pseudo-labels and returns inference probabilities.
                """
                optimizer = torch.optim.Adam(
                    self.model.parameters(), lr=0.01, weight_decay=5e-4
                )
                self.model.train()

                print("-" * 50)
                print("\t\t STARTING GRAPHSAGE TRAINING \t\t")
                print("-" * 50)

                for epoch in range(epochs):
                    optimizer.zero_grad()
                    logits_tr = self.model(data.x, data.edge_index)
                    loss = F.nll_loss(logits_tr, data.y)
                    loss.backward()
                    optimizer.step()

                    if epoch % 10 == 0:
                        print(f"Epoch: {epoch + 1} | Training Loss: {loss.item():.6f}")

                # Validation
                self.model.eval()
                with torch.no_grad():
                    logits_te = self.model(data.x, data, edge_index)
                    probabilies = torch.exp(logits_te)

                print("-" * 50)
                print("\t\t GRAPHSAGE INFERENCING COMPLETE \t\t")
                print("-" * 50)

                return probabilies
