import unittest

from anime_scene_finder.embedding import cosine_similarity
from anime_scene_finder.vector_store import vector_literal
from anime_scene_finder.media import representative_times


class CosineSimilarityTest(unittest.TestCase):
    def test_identical_vectors_score_one(self):
        self.assertAlmostEqual(cosine_similarity([1, 2, 3], [1, 2, 3]), 1.0)

    def test_mismatched_dimensions_fail(self):
        with self.assertRaises(ValueError):
            cosine_similarity([1], [1, 2])


class VectorLiteralTest(unittest.TestCase):
    def test_vector_literal_is_pgvector_compatible(self):
        self.assertEqual(vector_literal([1, 0.5, -2]), "[1.0,0.5,-2.0]")


class RepresentativeTimesTest(unittest.TestCase):
    def test_returns_three_interior_timestamps(self):
        self.assertEqual(representative_times(0, 10), [2.5, 5.0, 7.5])


if __name__ == "__main__":
    unittest.main()
