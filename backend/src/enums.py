from enum import Enum


class PathogenSource(str, Enum):
    HUMAN = "human"
    FOOD = "food"
    ANIMAL = "animal"
    ENVIRONMENT = "environment"
