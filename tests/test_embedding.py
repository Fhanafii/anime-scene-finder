import unittest

from anime_scene_finder.embedding import cosine_similarity


class CosineSimilarityTest(unittest.TestCase):
    def test_identical_vectors_score_one(self):
        self.assertAlmostEqual(cosine_similarity([1, 2, 3], [1, 2, 3]), 1.0)

    def test_mismatched_dimensions_fail(self):
        with self.assertRaises(ValueError):
            cosine_similarity([1], [1, 2])


if __name__ == "__main__":
    unittest.main()
