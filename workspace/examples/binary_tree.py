"""
二叉树 (Binary Tree) 示例

提供二叉树和二叉搜索树 (BST) 的常见操作实现，包括：
- 节点定义与构建
- 多种遍历方式 (前序、中序、后序、层序)
- 树的性质计算 (高度、节点数、是否为平衡树)
- 二叉搜索树 (BST) 的插入、搜索、删除
- 序列化与反序列化
"""

from __future__ import annotations

from collections import deque
from typing import Any, List, Optional


class TreeNode:
    """二叉树节点"""

    def __init__(self, val: Any = 0, left: Optional[TreeNode] = None, right: Optional[TreeNode] = None):
        self.val = val
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"TreeNode({self.val})"


# ========== 构建二叉树 ==========

def build_tree(values: List[Optional[Any]]) -> Optional[TreeNode]:
    r"""
    按层序遍历顺序构建二叉树。

    values 中的 None 表示该位置没有节点。

    例如:
        build_tree([1, 2, 3, None, 5, None, 7])
        表示::

              1
             / \
            2   3
             \   \
              5   7

    使用索引规则:
      根节点索引为 0
      左子节点索引为 2*i+1
      右子节点索引为 2*i+2
    """
    if not values or values[0] is None:
        return None

    nodes = [None] * len(values)
    # 先创建所有非 None 节点
    for i, v in enumerate(values):
        if v is not None:
            nodes[i] = TreeNode(v)

    # 再连接父子关系
    for i in range(len(values)):
        if nodes[i] is None:
            continue
        left_idx = 2 * i + 1
        right_idx = 2 * i + 2
        if left_idx < len(values):
            nodes[i].left = nodes[left_idx]
        if right_idx < len(values):
            nodes[i].right = nodes[right_idx]

    return nodes[0]


# ========== 遍历 ==========

def preorder_traversal(root: Optional[TreeNode]) -> List[Any]:
    """前序遍历: 根 -> 左 -> 右（递归）"""
    result = []

    def _dfs(node: Optional[TreeNode]) -> None:
        if node is None:
            return
        result.append(node.val)
        _dfs(node.left)
        _dfs(node.right)

    _dfs(root)
    return result


def inorder_traversal(root: Optional[TreeNode]) -> List[Any]:
    """中序遍历: 左 -> 根 -> 右（递归）"""
    result = []

    def _dfs(node: Optional[TreeNode]) -> None:
        if node is None:
            return
        _dfs(node.left)
        result.append(node.val)
        _dfs(node.right)

    _dfs(root)
    return result


def postorder_traversal(root: Optional[TreeNode]) -> List[Any]:
    """后序遍历: 左 -> 右 -> 根（递归）"""
    result = []

    def _dfs(node: Optional[TreeNode]) -> None:
        if node is None:
            return
        _dfs(node.left)
        _dfs(node.right)
        result.append(node.val)

    _dfs(root)
    return result


def levelorder_traversal(root: Optional[TreeNode]) -> List[List[Any]]:
    """
    层序遍历（广度优先），按层分组。

    返回格式: [[根], [第2层], [第3层], ...]
    """
    if root is None:
        return []

    result = []
    queue = deque([root])

    while queue:
        level_size = len(queue)
        level = []
        for _ in range(level_size):
            node = queue.popleft()
            level.append(node.val)
            if node.left:
                queue.append(node.left)
            if node.right:
                queue.append(node.right)
        result.append(level)

    return result


# ========== 树的性质 ==========

def tree_height(root: Optional[TreeNode]) -> int:
    """计算树的高度（根节点高度为 0）"""
    if root is None:
        return -1  # 空树高度为 -1
    return 1 + max(tree_height(root.left), tree_height(root.right))


def tree_size(root: Optional[TreeNode]) -> int:
    """计算树的节点总数"""
    if root is None:
        return 0
    return 1 + tree_size(root.left) + tree_size(root.right)


def is_balanced(root: Optional[TreeNode]) -> bool:
    """
    判断二叉树是否为平衡二叉树。
    任意节点的左右子树高度差不超过 1。
    """

    def _check(node: Optional[TreeNode]) -> int:
        """返回树的高度，如果失衡则返回 -1"""
        if node is None:
            return 0
        left = _check(node.left)
        if left == -1:
            return -1
        right = _check(node.right)
        if right == -1:
            return -1
        if abs(left - right) > 1:
            return -1
        return 1 + max(left, right)

    return _check(root) != -1


def is_symmetric(root: Optional[TreeNode]) -> bool:
    """判断二叉树是否为镜像对称"""

    def _is_mirror(t1: Optional[TreeNode], t2: Optional[TreeNode]) -> bool:
        if t1 is None and t2 is None:
            return True
        if t1 is None or t2 is None:
            return False
        return (t1.val == t2.val
                and _is_mirror(t1.left, t2.right)
                and _is_mirror(t1.right, t2.left))

    if root is None:
        return True
    return _is_mirror(root.left, root.right)


# ========== 二叉搜索树 (BST) ==========

def bst_insert(root: Optional[TreeNode], val: Any) -> TreeNode:
    """向 BST 中插入一个值"""
    if root is None:
        return TreeNode(val)

    if val < root.val:
        root.left = bst_insert(root.left, val)
    elif val > root.val:
        root.right = bst_insert(root.right, val)
    # 相等时不插入（去重）

    return root


def bst_search(root: Optional[TreeNode], val: Any) -> Optional[TreeNode]:
    """在 BST 中搜索一个值，返回节点或 None"""
    if root is None or root.val == val:
        return root

    if val < root.val:
        return bst_search(root.left, val)
    else:
        return bst_search(root.right, val)


def _bst_min_node(node: TreeNode) -> TreeNode:
    """找到 BST 中最小的节点（最左节点）"""
    while node.left:
        node = node.left
    return node


def bst_delete(root: Optional[TreeNode], val: Any) -> Optional[TreeNode]:
    """
    从 BST 中删除一个值。
    返回删除后的根节点。
    """
    if root is None:
        return None

    if val < root.val:
        root.left = bst_delete(root.left, val)
    elif val > root.val:
        root.right = bst_delete(root.right, val)
    else:
        # 找到要删除的节点
        # 情况 1: 叶子节点或只有一个子节点
        if root.left is None:
            return root.right
        if root.right is None:
            return root.left

        # 情况 2: 有两个子节点，用右子树的最小节点替换
        successor = _bst_min_node(root.right)
        root.val = successor.val
        root.right = bst_delete(root.right, successor.val)

    return root


def build_bst(values: List[Any]) -> Optional[TreeNode]:
    """用一组值构建 BST"""
    root = None
    for v in values:
        root = bst_insert(root, v)
    return root


# ========== 序列化与反序列化 ==========

def serialize(root: Optional[TreeNode]) -> str:
    """
    将二叉树序列化为字符串（层序，None 用 '#' 表示）。
    例如: "1,2,3,#,#,4,5"
    """
    if root is None:
        return ""

    result = []
    queue = deque([root])

    while queue:
        node = queue.popleft()
        if node is None:
            result.append("#")
        else:
            result.append(str(node.val))
            queue.append(node.left)
            queue.append(node.right)

    # 去除末尾的连续 "#"
    while result and result[-1] == "#":
        result.pop()

    return ",".join(result)


def deserialize(data: str) -> Optional[TreeNode]:
    """将序列化的字符串反序列化为二叉树"""
    if not data:
        return None

    values = data.split(",")
    if values[0] == "#":
        return None

    root = TreeNode(int(values[0]))
    queue = deque([root])
    i = 1

    while queue and i < len(values):
        node = queue.popleft()

        # 左子节点
        if i < len(values) and values[i] != "#":
            node.left = TreeNode(int(values[i]))
            queue.append(node.left)
        i += 1

        # 右子节点
        if i < len(values) and values[i] != "#":
            node.right = TreeNode(int(values[i]))
            queue.append(node.right)
        i += 1

    return root


# ========== 辅助工具 ==========

def print_tree(root: Optional[TreeNode], prefix: str = "", is_left: bool = True) -> None:
    """在控制台以易读格式打印二叉树"""
    if root is None:
        return

    print(prefix + ("+-- " if is_left else "+-- ") + str(root.val))

    if root.left or root.right:
        new_prefix = prefix + ("|   " if is_left else "    ")

        # 先打印右子树（在视觉上在上方）
        if root.right:
            print_tree(root.right, new_prefix, False)
        else:
            print(new_prefix + "+-- None")

        # 再打印左子树（在视觉上在下方）
        if root.left:
            print_tree(root.left, new_prefix, True)
        else:
            print(new_prefix + "+-- None")


def tree_to_list(root: Optional[TreeNode]) -> List[Optional[Any]]:
    """
    将二叉树转换为层序列表（与 build_tree 互逆）。
    不包含末尾的 None。
    """
    if root is None:
        return []

    result = []
    queue = deque([root])

    while queue:
        node = queue.popleft()
        if node is None:
            result.append(None)
        else:
            result.append(node.val)
            queue.append(node.left)
            queue.append(node.right)

    # 去除末尾的 None
    while result and result[-1] is None:
        result.pop()

    return result


# ===== 示例 =====

if __name__ == "__main__":
    print("=" * 50)
    print("1. 构建二叉树并遍历")
    print("=" * 50)

    # 构建一棵树:
    #       1
    #      / \
    #     2   3
    #    / \   \
    #   4   5   6
    values = [1, 2, 3, 4, 5, None, 6]
    root = build_tree(values)

    print("树结构:")
    print_tree(root)

    print(f"\n前序遍历:  {preorder_traversal(root)}")    # [1, 2, 4, 5, 3, 6]
    print(f"中序遍历:  {inorder_traversal(root)}")      # [4, 2, 5, 1, 3, 6]
    print(f"后序遍历:  {postorder_traversal(root)}")    # [4, 5, 2, 6, 3, 1]
    print(f"层序遍历:  {levelorder_traversal(root)}")   # [[1], [2, 3], [4, 5, 6]]

    print(f"\n树的高度: {tree_height(root)}")            # 2
    print(f"节点总数: {tree_size(root)}")               # 6
    print(f"是否平衡: {is_balanced(root)}")             # True

    print()
    print("=" * 50)
    print("2. 镜像对称树")
    print("=" * 50)

    #       1
    #      / \
    #     2   2
    #    / \ / \
    #   3  4 4  3
    sym_values = [1, 2, 2, 3, 4, 4, 3]
    sym_root = build_tree(sym_values)
    print(f"是否对称: {is_symmetric(sym_root)}")        # True

    # 不对称的树
    asym_values = [1, 2, 2, 3, 4, None, 3]
    asym_root = build_tree(asym_values)
    print(f"是否对称 (不对称): {is_symmetric(asym_root)}")  # False

    print()
    print("=" * 50)
    print("3. 二叉搜索树 (BST)")
    print("=" * 50)

    # 构建 BST:
    #       5
    #      / \
    #     3   8
    #    / \   \
    #   2   4   10
    bst_values = [5, 3, 8, 2, 4, 10]
    bst_root = build_bst(bst_values)

    print("BST 结构:")
    print_tree(bst_root)
    print(f"BST 中序遍历（应有序）: {inorder_traversal(bst_root)}")  # [2, 3, 4, 5, 8, 10]

    # 搜索
    target = 4
    found = bst_search(bst_root, target)
    print(f"\n搜索 {target}: {found}")

    target = 99
    found = bst_search(bst_root, target)
    print(f"搜索 {target}: {found}")

    # 删除
    print("\n删除节点 3:")
    bst_root = bst_delete(bst_root, 3)
    print_tree(bst_root)
    print(f"删除后中序遍历: {inorder_traversal(bst_root)}")  # [2, 4, 5, 8, 10]

    print()
    print("=" * 50)
    print("4. 序列化与反序列化")
    print("=" * 50)

    #       1
    #      / \
    #     2   3
    #        / \
    #       4   5
    tree = build_tree([1, 2, 3, None, None, 4, 5])
    serialized = serialize(tree)
    print(f"序列化:   {serialized}")                    # "1,2,3,#,#,4,5"

    deserialized = deserialize(serialized)
    print(f"反序列化: {tree_to_list(deserialized)}")    # [1, 2, 3, None, None, 4, 5]
    print(f"层序遍历:   {levelorder_traversal(deserialized)}")  # [[1], [2, 3], [4, 5]]
