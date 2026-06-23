"""
二叉树 (Binary Tree) 单元测试
"""

import pytest
from examples.binary_tree import (
    TreeNode,
    build_tree,
    build_bst,
    preorder_traversal,
    inorder_traversal,
    postorder_traversal,
    levelorder_traversal,
    tree_height,
    tree_size,
    is_balanced,
    is_symmetric,
    bst_insert,
    bst_search,
    bst_delete,
    serialize,
    deserialize,
    tree_to_list,
)


class TestBuildTree:
    """测试构建二叉树"""

    def test_empty(self):
        assert build_tree([]) is None
        assert build_tree([None]) is None

    def test_single_node(self):
        root = build_tree([1])
        assert root is not None
        assert root.val == 1
        assert root.left is None
        assert root.right is None

    def test_full_tree(self):
        root = build_tree([1, 2, 3, 4, 5, 6, 7])
        assert root.val == 1
        assert root.left.val == 2
        assert root.right.val == 3
        assert root.left.left.val == 4
        assert root.left.right.val == 5
        assert root.right.left.val == 6
        assert root.right.right.val == 7

    def test_tree_with_none(self):
        root = build_tree([1, None, 2, None, None, 3])
        assert root.val == 1
        assert root.left is None
        assert root.right.val == 2
        assert root.right.left.val == 3


class TestTraversal:
    """测试二叉树遍历"""

    def setup_method(self):
        #       1
        #      / \
        #     2   3
        #    / \   \
        #   4   5   6
        self.root = build_tree([1, 2, 3, 4, 5, None, 6])

    def test_preorder(self):
        assert preorder_traversal(self.root) == [1, 2, 4, 5, 3, 6]

    def test_inorder(self):
        assert inorder_traversal(self.root) == [4, 2, 5, 1, 3, 6]

    def test_postorder(self):
        assert postorder_traversal(self.root) == [4, 5, 2, 6, 3, 1]

    def test_levelorder(self):
        assert levelorder_traversal(self.root) == [[1], [2, 3], [4, 5, 6]]

    def test_empty_tree(self):
        assert preorder_traversal(None) == []
        assert inorder_traversal(None) == []
        assert postorder_traversal(None) == []
        assert levelorder_traversal(None) == []

    def test_single_node(self):
        root = TreeNode(42)
        assert preorder_traversal(root) == [42]
        assert inorder_traversal(root) == [42]
        assert postorder_traversal(root) == [42]
        assert levelorder_traversal(root) == [[42]]


class TestTreeProperties:
    """测试二叉树性质"""

    def setup_method(self):
        #       1
        #      / \
        #     2   3
        #    / \   \
        #   4   5   6
        self.root = build_tree([1, 2, 3, 4, 5, None, 6])

    def test_height(self):
        assert tree_height(self.root) == 2
        assert tree_height(None) == -1

    def test_size(self):
        assert tree_size(self.root) == 6
        assert tree_size(None) == 0

    def test_is_balanced(self):
        """树的高度差不超过 1"""
        assert is_balanced(self.root) is True

    def test_unbalanced_tree(self):
        #       1
        #      /
        #     2
        #    /
        #   3
        root = build_tree([1, 2, None, 3])
        assert is_balanced(root) is False

    def test_symmetric(self):
        sym_root = build_tree([1, 2, 2, 3, 4, 4, 3])
        assert is_symmetric(sym_root) is True

    def test_asymmetric(self):
        asym_root = build_tree([1, 2, 2, 3, 4, None, 3])
        assert is_symmetric(asym_root) is False

    def test_empty_symmetric(self):
        assert is_symmetric(None) is True


class TestBST:
    """测试二叉搜索树"""

    def setup_method(self):
        #       5
        #      / \
        #     3   8
        #    / \   \
        #   2   4   10
        self.root = build_bst([5, 3, 8, 2, 4, 10])

    def test_build_bst(self):
        assert inorder_traversal(self.root) == [2, 3, 4, 5, 8, 10]

    def test_search_found(self):
        node = bst_search(self.root, 4)
        assert node is not None
        assert node.val == 4

    def test_search_not_found(self):
        assert bst_search(self.root, 99) is None

    def test_search_empty(self):
        assert bst_search(None, 1) is None

    def test_insert(self):
        root = bst_insert(self.root, 6)
        assert bst_search(root, 6) is not None
        assert inorder_traversal(root) == [2, 3, 4, 5, 6, 8, 10]

    def test_insert_empty(self):
        root = bst_insert(None, 1)
        assert root is not None
        assert root.val == 1

    def test_delete_leaf(self):
        root = bst_delete(self.root, 10)
        assert inorder_traversal(root) == [2, 3, 4, 5, 8]

    def test_delete_one_child(self):
        root = bst_delete(self.root, 8)
        assert inorder_traversal(root) == [2, 3, 4, 5, 10]

    def test_delete_two_children(self):
        root = bst_delete(self.root, 3)
        assert inorder_traversal(root) == [2, 4, 5, 8, 10]

    def test_delete_root(self):
        root = bst_delete(self.root, 5)
        assert inorder_traversal(root) == [2, 3, 4, 8, 10]
        # 根节点变为 8（右子树最小节点）
        assert root.val == 8

    def test_delete_not_found(self):
        root = bst_delete(self.root, 99)
        assert inorder_traversal(root) == [2, 3, 4, 5, 8, 10]


class TestSerialize:
    """测试序列化与反序列化"""

    def test_serialize_empty(self):
        assert serialize(None) == ""

    def test_deserialize_empty(self):
        assert deserialize("") is None

    def test_roundtrip(self):
        #       1
        #      / \
        #     2   3
        #        / \
        #       4   5
        tree = build_tree([1, 2, 3, None, None, 4, 5])
        serialized = serialize(tree)
        assert serialized == "1,2,3,#,#,4,5"

        deserialized = deserialize(serialized)
        assert tree_to_list(deserialized) == [1, 2, 3, None, None, 4, 5]
        assert levelorder_traversal(deserialized) == [[1], [2, 3], [4, 5]]

    def test_single_node(self):
        assert serialize(TreeNode(42)) == "42"
        root = deserialize("42")
        assert root.val == 42

    def test_full_tree(self):
        tree = build_tree([1, 2, 3, 4, 5, 6, 7])
        data = serialize(tree)
        restored = deserialize(data)
        assert inorder_traversal(restored) == [4, 2, 5, 1, 6, 3, 7]


class TestTreeToList:
    """测试 tree_to_list 工具函数"""

    def test_empty(self):
        assert tree_to_list(None) == []

    def test_basic(self):
        root = build_tree([1, 2, 3, None, None, 4, 5])
        assert tree_to_list(root) == [1, 2, 3, None, None, 4, 5]

    def test_roundtrip(self):
        original = [1, 2, 3, None, 5, None, 7]
        root = build_tree(original)
        assert tree_to_list(root) == original


class TestEdgeCases:
    """测试边界情况"""

    def test_left_skewed(self):
        #   1
        #  /
        # 2
        #  \
        #   3
        root = build_tree([1, 2, None, None, 3])
        assert tree_height(root) == 2
        assert tree_size(root) == 3

    def test_right_skewed(self):
        # 1
        #  \
        #   2
        #    \
        #     3
        root = build_tree([1, None, 2, None, None, None, 3])
        assert tree_height(root) == 2
        assert tree_size(root) == 3

    def test_bst_duplicate(self):
        """BST 插入重复值不应增加节点"""
        root = build_bst([5, 3, 5, 3, 8])
        assert tree_size(root) == 3
        assert inorder_traversal(root) == [3, 5, 8]

    def test_deserialize_partial_tail(self):
        """末尾的 # 在序列化时被去除，反序列化应能正确处理"""
        data = "1,#,2"
        root = deserialize(data)
        assert root.val == 1
        assert root.left is None
        assert root.right.val == 2
