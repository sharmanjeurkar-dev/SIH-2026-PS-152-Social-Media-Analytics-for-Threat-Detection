import math
import os
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from torch_geometric.data import Data
from torch_geometric.utils import to_undirected

from src.model.gnnmodel import ThreatGraphSAGE


class GNNPIPELINE:
    """
    Translates NetworkX graphs into PyTorch Geometric tensors, generates robust
    pseudo-labels for zero-shot bootstrapping, and executes inductive ThreatGraphSAGE.
    """

    def __init__(self, hidden_dim: int = 32) -> None:
        self.num_features = 8
        # 0: ORGANIC_USER, 1: BOT, 2: MALICIOUS_ACTOR
        self.target_classifiers = 3
        self.target_names = ["ORGANIC_USER", "BOT", "MALICIOUS_ACTOR"]
        self.model = ThreatGraphSAGE(
            in_channels=self.num_features,
            out_channels=self.target_classifiers,
            hidden_channels=hidden_dim,
            dropout=0.3,
        )

    def networkx_to_pyg(self, G: nx.DiGraph, node_metadata: dict) -> Tuple[Data, list]:
        """
        Converts the NetworkX DiGraph into a PyG Data object.
        Fuses topological metrics, user profile data, and NLP threat signals into the feature tensor.
        """
        if len(G) == 0:
            empty_x = torch.empty((0, self.num_features), dtype=torch.float)
            empty_edge = torch.empty((2, 0), dtype=torch.long)
            empty_y = torch.empty((0,), dtype=torch.long)
            return Data(x=empty_x, edge_index=empty_edge, y=empty_y), []

        print("Computing fast PageRank across graph...")
        pagerank_scores = nx.pagerank(G, alpha=0.85, max_iter=50, weight="weight")

        node_mapping = {node: i for i, node in enumerate(G.nodes())}
        reverse_mapping = list(G.nodes())

        x_features = []
        pseudo_labels = []

        # Find median PageRank for influence thresholding
        pr_values = list(pagerank_scores.values())
        median_pr = float(np.median(pr_values)) if pr_values else 0.0001

        for node in G.nodes():
            in_deg = float(G.in_degree(node))
            out_deg = float(G.out_degree(node))
            amp_ratio = (in_deg + 1.0) / (out_deg + 1.0)
            pr = float(pagerank_scores.get(node, 0.0))

            meta = node_metadata.get(node, {})
            followers = float(meta.get("followers_count", 0) or 0)
            following = float(meta.get("following_count", 0) or 0)
            toxicity = float(meta.get("avg_toxicity", 0.0) or 0.0)
            follower_ratio = (followers + 1.0) / (followers + following + 2.0)

            # Build 8-dimensional normalized feature vector
            feat_vector = [
                min(math.log1p(in_deg) / 5.0, 1.0),
                min(math.log1p(out_deg) / 5.0, 1.0),
                min(amp_ratio / 5.0, 1.0),
                min(pr * 10000.0, 1.0),
                min(math.log1p(followers) / 10.0, 1.0),
                min(math.log1p(following) / 10.0, 1.0),
                min(follower_ratio, 1.0),
                min(toxicity, 1.0),
            ]
            x_features.append(feat_vector)

            # Multi-factor heuristic pseudo-labeling
            is_bot = (
                (following > 50 and followers < 10)
                or (follower_ratio < 0.05 and following > 20)
                or (out_deg >= 2 and amp_ratio < 0.2 and followers < 50)
            )

            is_malicious = (
                (toxicity >= 0.25)
                or (toxicity >= 0.1 and pr >= median_pr)
            )

            if is_malicious:
                pseudo_labels.append(2)  # MALICIOUS_ACTOR
            elif is_bot:
                pseudo_labels.append(1)  # BOT
            else:
                pseudo_labels.append(0)  # ORGANIC_USER

        # Convert to PyTorch Tensors
        x = torch.tensor(x_features, dtype=torch.float)
        y = torch.tensor(pseudo_labels, dtype=torch.long)

        # Build directed edge index
        edges = [(node_mapping[u], node_mapping[v]) for u, v in G.edges()]
        if not edges:
            edge_index = torch.empty((2, 0), dtype=torch.long)
        else:
            directed_edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
            # Convert to bidirectional graph for GraphSAGE 2-hop message passing
            edge_index = to_undirected(directed_edge_index, num_nodes=len(reverse_mapping))

        data = Data(x=x, edge_index=edge_index, y=y)

        # Log class distribution
        bincount = torch.bincount(y, minlength=self.target_classifiers).tolist()
        print(f"Converted to PyG Data: {data.num_nodes} nodes, {data.num_edges} bidirectional edges.")
        print(
            f"Class Distribution -> Organic: {bincount[0]}, Bot: {bincount[1]}, Malicious: {bincount[2]}"
        )

        return data, reverse_mapping

    def _split_train_test(self, data: Data, test_size: float = 0.2) -> Tuple[torch.Tensor, torch.Tensor]:
        """Creates stratified train and test masks to guarantee all classes are present."""
        num_nodes = data.num_nodes
        indices = np.arange(num_nodes)
        y_np = data.y.cpu().numpy()

        # Check if stratified split is possible (minimum 2 samples per present class)
        class_counts = np.bincount(y_np, minlength=self.target_classifiers)
        can_stratify = all(c >= 2 for c in class_counts if c > 0)

        if can_stratify and len(np.unique(y_np)) > 1:
            try:
                train_idx, test_idx = train_test_split(
                    indices, test_size=test_size, stratify=y_np, random_state=42
                )
            except ValueError:
                train_idx, test_idx = train_test_split(indices, test_size=test_size, random_state=42)
        else:
            train_idx, test_idx = train_test_split(indices, test_size=test_size, random_state=42)

        train_mask = torch.zeros(num_nodes, dtype=torch.bool)
        test_mask = torch.zeros(num_nodes, dtype=torch.bool)
        train_mask[train_idx] = True
        test_mask[test_idx] = True

        return train_mask, test_mask

    def evaluate_model_performance(self, model: torch.nn.Module, data: Data, test_mask: torch.Tensor):
        model.eval()
        with torch.no_grad():
            out = model(data.x, data.edge_index)
            preds = out.argmax(dim=1)

        y_true = data.y[test_mask].cpu().numpy()
        y_pred = preds[test_mask].cpu().numpy()

        print("\n--- TEST SET CLASSIFICATION REPORT ---")
        print(
            classification_report(
                y_true,
                y_pred,
                labels=[0, 1, 2],
                target_names=self.target_names,
                zero_division=0,
            )
        )

        print("--- CONFUSION MATRIX ---")
        print(confusion_matrix(y_true, y_pred, labels=[0, 1, 2]))

    def train_and_predict(
        self, data: Data, epochs: int = 50, save_path: str = "models/threat_graphsage.pt"
    ) -> torch.Tensor:
        """
        Trains the ThreatGraphSAGE model with stratified train/test split,
        inverse class weighting, and model checkpoint serialization.
        """
        if data.num_nodes == 0:
            return torch.empty((0, self.target_classifiers))

        train_mask, test_mask = self._split_train_test(data, test_size=0.2)

        # Compute inverse class weights strictly on training set
        y_train = data.y[train_mask]
        class_counts = torch.bincount(y_train, minlength=self.target_classifiers).float()
        class_counts = torch.clamp(class_counts, min=1.0)

        total_train = y_train.size(0)
        class_weights = total_train / (self.target_classifiers * class_counts)
        class_weights = class_weights.to(data.x.device)

        optimizer = torch.optim.Adam(
            self.model.parameters(), lr=0.01, weight_decay=1e-4
        )

        self.model.train()
        print("-" * 50)
        print("\t\t STARTING GRAPHSAGE TRAINING \t\t")
        print("-" * 50)

        for epoch in range(epochs):
            optimizer.zero_grad()
            logits = self.model(data.x, data.edge_index)

            # Train strictly on the train mask
            loss = F.nll_loss(logits[train_mask], data.y[train_mask], weight=class_weights)
            loss.backward()
            optimizer.step()

            if epoch % 10 == 0 or epoch == epochs - 1:
                # Compute training accuracy
                train_preds = logits[train_mask].argmax(dim=1)
                train_acc = (train_preds == data.y[train_mask]).float().mean().item()
                print(
                    f"Epoch: {epoch + 1:02d}/{epochs} | Loss: {loss.item():.5f} | Train Acc: {train_acc * 100:.1f}%"
                )

        # Full Graph Inference
        self.model.eval()
        with torch.no_grad():
            full_logits = self.model(data.x, data.edge_index)
            probabilities = torch.exp(full_logits)

        print("-" * 50)
        print("\t\t GRAPHSAGE INFERENCING COMPLETE \t\t")
        print("-" * 50)

        self.evaluate_model_performance(model=self.model, data=data, test_mask=test_mask)

        # Save model checkpoint
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save(self.model.state_dict(), save_path)
            print(f"[SUCCESS] Model checkpoint saved to: {save_path}")
        except Exception as e:
            print(f"[WARN] Could not save model checkpoint: {e}")

        return probabilities
