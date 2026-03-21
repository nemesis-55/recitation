from app.utils.image_utils import sort_boxes_reading_order


def test_sort_boxes_reading_order():
    boxes = [(100, 10, 20, 20), (10, 8, 20, 20), (5, 100, 20, 20)]
    ordered = sort_boxes_reading_order(boxes)
    assert ordered[0][0] == 10
    assert ordered[1][0] == 100
    assert ordered[2][1] == 100
