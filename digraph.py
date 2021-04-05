class Digraph:
    def __init__(self):
        self._neighbors_A_d = dict()
        self._neighbors_B_d = dict()

    def nodes_A(self):
        return self._neighbors_A_d.keys()
    def nodes_B(self):
        return self._neighbors_B_d.keys()

    def add_node_A(self, A):
        assert A not in self._neighbors_A_d
        self._neighbors_A_d[A] = set()
        #self.check_correct()
    def add_node_B(self, B):
        assert B not in self._neighbors_B_d
        self._neighbors_B_d[B] = set()
        #self.check_correct()
    def add_node(self, node):
        self.add_node_A(node)
        self.add_node_B(node)

    def add_edge(self, A, B):
        self._neighbors_A_d[A].add(B)
        self._neighbors_B_d[B].add(A)
        #self.check_correct()

    def neighbors_A(self, A):
        return self._neighbors_A_d[A]
    def neighbors_B(self, B):
        return self._neighbors_B_d[B]

    def remove_node_A(self, A):
        for B in self._neighbors_A_d[A]:
            self._neighbors_B_d[B].remove(A)
        del self._neighbors_A_d[A]
        #self.check_correct()
    def remove_node_B(self, B):
        for A in self._neighbors_B_d[B]:
            self._neighbors_A_d[A].remove(B)
        del self._neighbors_B_d[B]
        #self.check_correct()
    def remove_node(self, node):
        self.remove_node_A(node)
        self.remove_node_B(node)

    def closure(self, start_list, get_neighbors):
        stack = list(start_list)
        res = set()
        while stack:
            x = stack.pop()
            if x in res: continue
            res.add(x)
            stack.extend(get_neighbors(x))
        return res

    def closure_AB(self, start_list):
        return self.closure(
            start_list,
            lambda A: self._neighbors_A_d.get(A, []),
        )
    def closure_BA(self, start_list):
        return self.closure(
            start_list,
            lambda B: self._neighbors_B_d.get(B, [])
        )

    def check_correct(self):
        for A, Bs in self._neighbors_A_d.items():
            for B in Bs:
                assert A in self._neighbors_B_d[B]

if __name__ == "__main__":
    graph = Digraph()
    graph.add_node_A(5)
    graph.add_node_B(10)
    graph.add_edge(a0, b0)
