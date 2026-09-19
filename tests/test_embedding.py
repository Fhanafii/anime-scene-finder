import unittest

from app.embedding import cosine_similarity
from app.vector_store import vector_literal
from app.media import representative_times
from app.aggregation import aggregate_scene_matches
from app.vector_store import VectorMatch
from app.hybrid import fuse_scores
from app.ocr import normalize_text, text_similarity


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


class SceneAggregationTest(unittest.TestCase):
    def test_groups_frames_and_keeps_best_match_per_scene(self):
        def match(frame_id, scene_id, similarity):
            return VectorMatch(frame_id, scene_id, float(frame_id), "key.jpg", similarity, 1, "Anime", 2, 1, 1, None, 0, 1, 0.5)

        results = aggregate_scene_matches([match(1, 10, 0.8), match(2, 10, 0.95), match(3, 11, 0.9)], 10)
        self.assertEqual([candidate.match.scene_id for candidate in results], [10, 11])
        self.assertEqual(results[0].match.frame_id, 2)
        self.assertEqual(results[0].frame_count, 2)


class HybridSearchTest(unittest.TestCase):
    def test_ocr_signal_boosts_matching_candidate(self):
        self.assertEqual(normalize_text("Hello, WORLD!"), "hello world")
        self.assertEqual(text_similarity("hello", "hello world"), 1.0)
        ocr_score, final_score = fuse_scores(0.5, "hello", "hello world")
        self.assertEqual(ocr_score, 1.0)
        self.assertAlmostEqual(final_score, 0.6)


if __name__ == "__main__":
    unittest.main()
