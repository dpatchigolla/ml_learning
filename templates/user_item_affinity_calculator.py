
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.recommendation import ALS
from pyspark import SparkContext
from pyspark.sql import SQLContext
from pyspark.sql import HiveContext
from pyspark.ml.feature import StringIndexer
from pyspark.sql.types import IntegerType
from pyspark.sql.types import DoubleType
from pyspark.sql.functions import explode
from pyspark.sql.functions import udf
from pyspark.sql.window import Window
from pyspark.sql.functions import *
import sys
import pyspark.sql.functions as sf
from pyspark.sql.functions import lit
from pyspark.sql.types import StringType
import logging
import datetime


sc = SparkContext()
hc = HiveContext(sc)
sqlContext = SQLContext(sc)

###########

def print_with_time(str_to_print):
	currentDT = datetime.datetime.now()
	print (str(currentDT)+": "+str_to_print)


class RankBasedEvaluator2():
	
	def __init__(self, user_col, rating_col, prediction_col):
		self._user_col = user_col
		self._rating_col = rating_col
		self._prediction_col = prediction_col
	
	def evaluate(self, spark, predictions):
		predictions.createOrReplaceTempView("original_predictions")
		# I filter out NaN predictions
		spark.sql("""SELECT *
                     FROM original_predictions
                     WHERE NOT ISNAN({0})""".format(self._prediction_col)) \
			.createOrReplaceTempView("predictions")
		spark.sql("""SELECT {0}
                          , SUM({1}) as rating_sum
                     FROM predictions
                     GROUP BY {0}""".format(self._user_col, self._rating_col)) \
			.createOrReplaceTempView("rating_sums")
		spark.sql("""SELECT {0}
                          , {1}
                          , PERCENT_RANK() OVER (PARTITION BY {0} ORDER BY {2} DESC) AS rank
                     FROM predictions""".format(self._user_col, self._rating_col,
												self._prediction_col)) \
			.createOrReplaceTempView("ratings_with_ranks")
		spark.sql("""SELECT {0},
                     SUM({1} * rank) AS weighted_sum
                     FROM ratings_with_ranks
                     GROUP BY {0}""".format(self._user_col, self._rating_col)) \
			.createOrReplaceTempView("weighted_rating_sums")
		spark.sql("""SELECT weighted_rating_sums.*, rating_sums.rating_sum
                     FROM weighted_rating_sums
                     JOIN rating_sums
                       ON weighted_rating_sums.{0} = rating_sums.{0}""".format(self._user_col)) \
			.createOrReplaceTempView("joined_sums")
		
		result = spark.sql("""SELECT AVG(weighted_sum / rating_sum)
                              FROM joined_sums""")
		
		return result.collect()[0][0]

class user_item_affinity_calculator:
	
	def __init__(self, input_ratings_location,
				 output_recommendation_location,
				 user_features_location,
				 item_features_location,
				 rating_cutoff,
				 entity_type):
		self.input_ratings_location = input_ratings_location
		self.output_recommendation_location = output_recommendation_location
		self.user_features_location = user_features_location
		self.item_features_location = item_features_location
		self.rating_cutoff = rating_cutoff
		self.entity_type = entity_type
	
	def read_data_from_gs_location(self):
		
		logging.info("constructing the rdd from the ratings file")
		print_with_time("constructing the rdd from the ratings file")
		rdd = sc.textFile(self.input_ratings_location).map(lambda x: x.split(","))
		
		logging.info("creating the dataframe")
		print_with_time("creating the dataframe")
		self.df = hc.createDataFrame(rdd, ["user_id", "item_id", "rating"])
		self.df = self.df.withColumn("rating", self.df["rating"].cast("double"))
		
		grouped_df = self.df.groupBy("user_id").agg(sf.count('rating').alias('unique_ratings'))
		filtered_df = grouped_df.filter(grouped_df.unique_ratings > self.rating_cutoff)
		self.df = self.df.join(filtered_df, ["user_id"], 'inner')
		self.df = self.df.select(["user_id", "item_id", "rating"])
		self.df.cache()
	
	def build_recommendation_model(self):
		logging.info("getting distinct users")
		print_with_time("getting distinct users")
		users = self.df.select(["user_id"]).distinct()
		
		logging.info("getting distinct items")
		print_with_time("getting distinct items")
		items = self.df.select(["item_id"]).distinct()
		
		logging.info("mapping user_id to number")
		print_with_time("mapping user_id to number")
		user_indexer = StringIndexer(inputCol="user_id", outputCol="user_id_no")
		self.user_indexed = user_indexer.fit(users).transform(users)
		self.user_indexed = self.user_indexed.select(self.user_indexed.user_id.cast("string"), self.user_indexed.user_id_no.cast("int"))
		
		logging.info("mapping item_id to number")
		print_with_time("mapping item_id to number")
		item_indexer = StringIndexer(inputCol="item_id", outputCol="item_id_no")
		self.item_indexed = item_indexer.fit(items).transform(items)
		self.item_indexed = self.item_indexed.select(self.item_indexed.item_id.cast("string"), self.item_indexed.item_id_no.cast("int"))
		
		logging.info("joining df with user_indexed rdd")
		print_with_time("joining df with user_indexed rdd")
		self.df = self.df.join(self.user_indexed, ["user_id"], 'inner')
		
		logging.info("joining df with item_indexed rdd")
		print_with_time("joining df with item_indexed rdd")
		self.df = self.df.join(self.item_indexed, ["item_id"], 'inner')
		self.df = self.df.select(["item_id_no", "user_id_no", "rating"])
		
		############
		
		logging.info("splitting dataset into training and testing")
		print_with_time("splitting dataset into training and testing")
		(training, validation, test) = self.df.randomSplit([0.6, 0.2, 0.2])
		
		######
		
		ranks = [25, 50, 100]
		regParam = [0.1, 0.01, 0.001]
		all_params = [(rank, reg) for rank in ranks for reg in regParam]
		
		min_mpr = float('inf')
		best_rank = -1
		best_reg = -1
		for (iteration_no, (rank, reg)) in enumerate(all_params):
			
			logging.info(iteration_no)
			print_with_time(str(iteration_no))
			logging.info("rank=%s, reg=%s " % (rank, reg))
			print_with_time("rank=%s, reg=%s " % (rank, reg))
			
			als = ALS(rank=rank,
					  regParam=reg,
					  nonnegative=True,
					  implicitPrefs=True,
					  userCol="user_id_no",
					  itemCol="item_id_no",
					  checkpointInterval=-1,
					  coldStartStrategy="drop",
					  ratingCol="rating")
			self.model = als.fit(training)
			
			logging.info("transforming the validation set")
			print_with_time("transforming the validation set")
			predictions = self.model.transform(validation)
			
			logging.info("getting rmse on validation set")
			print_with_time("getting rmse on validation set")
			
			evaluator = RegressionEvaluator(metricName="rmse", labelCol="rating", predictionCol="prediction")
			rmse = evaluator.evaluate(predictions)
			logging.info("Root-mean-square error = " + str(rmse))
			print_with_time("Root-mean-square error = " + str(rmse))
			
			logging.info("getting MPR on validation set")
			print_with_time("getting MPR on validation set")
			
			ev = RankBasedEvaluator2("user_id_no", "rating", "prediction")
			mpr = ev.evaluate(sqlContext, predictions)
			logging.info("Mean Percentile Ranking = " + str(mpr))
			print_with_time("Mean Percentile Ranking = " + str(mpr))
			
			if mpr < min_mpr:
				min_mpr = mpr
				best_rank = rank
				best_reg = reg
		
		logging.info('The best model was trained with rank %s and reg %s' % (best_rank, best_reg))
		print_with_time('The best model was trained with rank %s and reg %s' % (best_rank, best_reg))
		
		######
		
		
		logging.info("starting model training")
		print_with_time("starting model training")
		
		als = ALS(rank=best_rank,
				  regParam=best_reg,
				  nonnegative=True,
				  implicitPrefs=True,
				  userCol="user_id_no",
				  itemCol="item_id_no",
				  checkpointInterval=-1,
				  coldStartStrategy="drop",
				  ratingCol="rating")
		self.model = als.fit(training)
		
		logging.info("transforming the test set")
		print_with_time("transforming the test set")
		predictions = self.model.transform(test)
		
		logging.info("getting rmse on test set")
		print_with_time("getting rmse on test set")
		
		evaluator = RegressionEvaluator(metricName="rmse", labelCol="rating", predictionCol="prediction")
		rmse = evaluator.evaluate(predictions)
		logging.info("Root-mean-square error = " + str(rmse))
		print_with_time("Root-mean-square error = " + str(rmse))
		
		logging.info("getting MPR on test set")
		print_with_time("getting MPR on test set")
		ev = RankBasedEvaluator2("user_id_no", "rating", "prediction")
		mpr = ev.evaluate(sqlContext, predictions)
		logging.info("Mean Percentile Ranking = " + str(mpr))
		print_with_time("Mean Percentile Ranking = " + str(mpr))
	
	def dump_recommendations_to_gs_location(self):
		logging.info("gettinmg top 100 recommendations for all users")
		print_with_time("gettinmg top 100 recommendations for all users")
		userRecs = self.model.recommendForAllUsers(100)
		
		logging.info("explode function - converting array to rows")
		print_with_time("explode function - converting array to rows")
		userRecs = userRecs.withColumn("recommendations", explode(userRecs.recommendations))
		
		logging.info("splitting recommendation array into item_id & affinity score")
		print_with_time("splitting recommendation array into item_id & affinity score")
		
		func_first_udf = udf(lambda x: x[0], IntegerType())
		func_second_udf = udf(lambda x: x[1], DoubleType())
		userRecs = userRecs.withColumn("item_id_no", func_first_udf(userRecs['recommendations']))
		userRecs = userRecs.withColumn("affinity", func_second_udf(userRecs['recommendations']))
		userRecs = userRecs.select(["user_id_no", "item_id_no", "affinity"])
		
		logging.info("converting back user_id_no & item_id_no into user_id & item_id")
		print_with_time("converting back user_id_no & item_id_no into user_id & item_id")
		
		userRecs = userRecs.join(self.user_indexed, ["user_id_no"], 'inner')
		userRecs = userRecs.join(self.item_indexed, ["item_id_no"], 'inner')
		userRecs = userRecs.select(["user_id", "item_id", "affinity"])
		
		logging.info("applying window function to keep user_id rows together & adding rank column")
		print_with_time("applying window function to keep user_id rows together & adding rank column")
		userRecs = userRecs.withColumn("rank",
									   dense_rank().over(Window.partitionBy("user_id").orderBy(desc("affinity"))))
		
		#########
		
		userRecs = userRecs.withColumn("entity_type", lit(self.entity_type))
		userRecs = userRecs.select(["user_id", "entity_type", "item_id", "affinity"])
		
		logging.info("storing recommendation output in the gs location")
		print_with_time("storing recommendation output in the gs location")
		userRecs.write.format("csv").save(output_recommendation_location, mode="append")
		
		logging.info("getting the user factors")
		print_with_time("getting the user factors")
		user_factors = self.model.userFactors
		user_factors_df = self.user_indexed.join(user_factors,
												 self.user_indexed.user_id_no == user_factors.id,
												 'inner').select(["user_id", "features"])
		array_to_string = lambda my_list: '[' + ','.join([str(elem) for elem in my_list]) + ']'
		array_to_string_udf = udf(array_to_string, StringType())
		user_factors_string_df = user_factors_df.withColumn('features_string', array_to_string_udf(user_factors_df["features"]))
		
		logging.info("storing the user factors")
		print_with_time("storing the user factors")
		user_factors_string_df.drop("features").write.format("csv").save(user_features_location,
																		 mode="append")
		
		logging.info("getting the item factors")
		print_with_time("getting the item factors")
		item_factors = self.model.itemFactors
		item_factors_df = self.item_indexed.join(item_factors,
												 self.item_indexed.item_id_no == item_factors.id,
												 'inner').select(["item_id", "features"])
		item_factors_string_df = item_factors_df.withColumn('features_string',
															array_to_string_udf(item_factors_df["features"]))
		
		logging.info("storing the item factors")
		print_with_time("storing the item factors")
		item_factors_string_df.drop("features").write.format("csv").save(item_features_location,
																		 mode="append")
		
		print_with_time("done with storing user and item factors")
	
	def recommendation_handler(self):
		
		print_with_time("reading data from gs location")
		self.read_data_from_gs_location()
		print_with_time("building recommendation model")
		self.build_recommendation_model()
		print_with_time("dumping recommendation to gs location")
		self.dump_recommendations_to_gs_location()
		print_with_time("finished everything")
		

if __name__ == "__main__":
	input_ratings_location = sys.argv[1]
	output_recommendation_location = sys.argv[2]
	user_features_location = sys.argv[3]
	item_features_location = sys.argv[4]
	rating_cutoff = int(sys.argv[5])
	entity_type = str(sys.argv[6])
	
	affinity_calculator = user_item_affinity_calculator(input_ratings_location,
														output_recommendation_location,
														user_features_location,
														item_features_location,
														rating_cutoff,
														entity_type)
	affinity_calculator.recommendation_handler()


