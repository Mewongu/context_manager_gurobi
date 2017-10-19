# Structured modelling with context managers and gurobi

This project serves as an example of how you can use context managers to construct your gurobi model. 
  
The example used is a knapsack problem where you have three top level constraints that can be combined in several different ways.


To modify the model remove or add constraints on line 205


Requirements:
python 3.6.1
gurobi 7.5.1

```bash
#> python knapsack.py volume
#> python knapsack.py weight
#> python knapsack.py value

```
