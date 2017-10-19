"""
Author: Andreas Stenberg
Date: 20171019
Description:
    Usage of context managers for structured modelling with gurobi
"""
import sys

from collections import OrderedDict
from functools import reduce
from typing import List

import gurobipy


def merge_dicts(a, b):
    merged = OrderedDict()
    for key, val in a.items():
        if key not in b:
            merged[key] = val
        else:
            if isinstance(val, dict) and isinstance(b[key], dict):
                merged[key] = merge_dicts(a[key], b[key])
            else:
                raise RuntimeError('Error merging {a} and {b}')
    for key, val in b.items():
        if key in merged:
            continue
        merged[key] = val
    return merged


class Carrier:
    def __init__(self, name, weight_capacity):
        self.name = name
        self.weight = weight_capacity


class Bag:
    def __init__(self, name, volume_capacity, weight_capacity):
        self.name = name
        self.volume = volume_capacity
        self.weight = weight_capacity


class Item:
    def __init__(self, name, volume_requirement, weight_requirement, value, available_count=2**31, requirement=0):
        self.name = name
        self.volume = volume_requirement
        self.weight = weight_requirement
        self.value = value
        self.available = available_count
        self.requirement = requirement


class Vars:
    def __init__(self, model, *args, **kwargs):
        self._vars = OrderedDict()
        self.model = model

    @property
    def vars(self):
        return self._vars

    @vars.setter
    def set_vars(self, v):
        self._vars = merge_dicts(self._vars, v)

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        pass


class Constraints(Vars):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.constraints = OrderedDict()

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        pass


class BagVars(Vars):
    def __init__(self, bags: List[Bag], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bags = bags

    def __enter__(self):
        super().__enter__()
        for bag in self.bags:
            self.vars[bag.name] = OrderedDict()
            self.vars[bag.name]['weight'] = self.model.addVar(vtype=gurobipy.GRB.CONTINUOUS, lb=0, ub=bag.weight, name=f'Bag({bag.name})_weight')
            self.vars[bag.name]['volume'] = self.model.addVar(vtype=gurobipy.GRB.CONTINUOUS, lb=0, ub=bag.volume, name=f'Bag({bag.name})_volume')
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class ItemVars(Vars):
    def __init__(self, items, *args,  **kwargs):
        super().__init__(*args, **kwargs)
        self.items = items

    def __enter__(self):
        super().__enter__()
        for item in self.items:
            self.vars[item.name] = OrderedDict()
            self.vars[item.name]['count'] = self.model.addVar(vtype=gurobipy.GRB.INTEGER, lb=0, ub=item.available, name=f'Item({item.name})_count')
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class ItemsInBagVars(BagVars, ItemVars):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __enter__(self):
        super().__enter__()
        for bag in self.bags:
            for item in self.items:
                if item.name not in self.vars[bag.name]:
                    self.vars[bag.name][item.name] = OrderedDict()
                self.vars[bag.name][item.name]['count'] = self.model.addVar(vtype=gurobipy.GRB.INTEGER, lb=0, ub=item.available, name=f'Item({item.name})_count_in_Bag({bag.name})')
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class CarrierConstraints(ItemVars, Constraints):
    def __init__(self, carrier: Carrier, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.carrier = carrier

    def __enter__(self):
        super().__enter__()
        self.constraints[self.carrier.name] = OrderedDict()
        weight_sum_expr = reduce(lambda a, b: a + b,
                                 [self.vars[item.name]['count'] * item.weight
                                  for item in self.items])
        self.constraints[carrier.name]['weight'] = model.addConstr(weight_sum_expr <= self.carrier.weight)
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class ItemInBagConstraints(ItemsInBagVars, Constraints):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __enter__(self):
        super().__enter__()
        for bag in self.bags:
            if bag.name not in self.constraints:
                self.constraints[bag.name] = OrderedDict()
            weight_sum_expr = reduce(lambda a, b: a + b,
                                     [self.vars[bag.name][item.name][
                                          'count'] * item.weight
                                      for item in self.items])
            self.constraints[bag.name][
                'weight'] = model.addConstr(weight_sum_expr <= bag.weight)
            volume_sum_expr = reduce(lambda a, b: a + b,
                                     [self.vars[bag.name][item.name][
                                          'count'] * item.volume
                                      for item in self.items])
            self.constraints[bag.name][
                'volume'] = model.addConstr(volume_sum_expr <= bag.volume)

        for item in self.items:
            if item.name not in self.constraints:
                self.constraints[item.name] = OrderedDict()
            item_count = reduce(lambda a, b: a + b, [self.vars[bag.name][item.name]['count'] for bag in self.bags])
            self.constraints[item.name]['total'] = model.addConstr(item_count == self.vars[item.name]['count'])
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class ItemRequirementConstraints(ItemVars):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __enter__(self):
        super().__enter__()
        for item in self.items:
            if item.name not in self.constraints:
                self.constraints[item.name] = OrderedDict()
            self.constraints[item.name]['required'] = self.model.addConstr(self.vars[item.name]['count'] >= item.requirement)

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


# Modify the base model by removing constraints here
class BaseModel(ItemInBagConstraints, CarrierConstraints, ItemRequirementConstraints):
    pass


class MaxVolumeGoal(BaseModel):
    def __init__(self, *args, **kwargs):
        super(MaxVolumeGoal, self).__init__(*args, **kwargs)

    def __enter__(self):
        super().__enter__()
        volume_expr = reduce(lambda a, b: a + b,
                                 [self.vars[item.name]['count'] * item.volume
                                  for item in self.items])
        self.model.setObjective(volume_expr, gurobipy.GRB.MAXIMIZE)
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class MaxValueGoal(BaseModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __enter__(self):
        super().__enter__()
        value_expr = reduce(lambda a, b: a + b,
                                 [self.vars[item.name]['count'] * item.value
                                  for item in self.items])
        self.model.setObjective(value_expr, gurobipy.GRB.MAXIMIZE)
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


class MaxWeightGoal(BaseModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __enter__(self):
        super().__enter__()
        weight_expr = reduce(lambda a, b: a + b,
                                 [self.vars[item.name]['count'] * item.weight
                                  for item in self.items])
        self.model.setObjective(weight_expr, gurobipy.GRB.MAXIMIZE)
        return self

    def __exit__(self, a, b, c):
        super().__exit__(a, b, c)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ['volume', 'weight', 'value']:
        print('You must supply exactly one argument [volume, weight, value]')
        sys.exit(-1)
    conversion_map = {
        'volume': MaxVolumeGoal,
        'weight': MaxWeightGoal,
        'value': MaxValueGoal
    }

    carrier = Carrier('John', weight_capacity=200)
    bags = [
        Bag('Osprey 32L', volume_capacity=32, weight_capacity=15),
        Bag('Osprey 60L', volume_capacity=60, weight_capacity=25)
    ]
    items = [
        Item('Gascan 650ml', volume_requirement=0.700, weight_requirement=0.600, available_count=4, value=240),
        Item('Tent 2man', volume_requirement=13, weight_requirement=3.5, available_count=1, value=2000, requirement=1),
        Item('Tent 3man', volume_requirement=16, weight_requirement=4.5, available_count=1, value=2500),
        Item('Tent 4man', volume_requirement=18, weight_requirement=5.5, available_count=1, value=3000),
        Item('Axe', volume_requirement=2, weight_requirement=4, available_count=1, value=1000),
        Item('Knife', volume_requirement=0.3, weight_requirement=0.250, available_count=1, value=400),
        Item('FoodPortion', volume_requirement=0.300, weight_requirement=0.400, value=80),
        Item('Water', volume_requirement=1, weight_requirement=1, value=5),
        Item('Portable Kitchen', volume_requirement=2, weight_requirement=1, available_count=1, value=800, requirement=1),
        Item('Sleeping Bag', volume_requirement=4, weight_requirement=0.900, available_count=4, value=1400, requirement=1)
    ]

    model = gurobipy.Model()
    kwargs = {'carrier':carrier, 'bags':bags, 'items':items, 'model':model}
    with conversion_map[sys.argv[1]](**kwargs) as base:
        model.optimize()

        print('\n=== Items brought ===\n')
        for bag in bags:
            print(f'---Items in {bag.name}---')
            for item in items:
                if base.vars[bag.name][item.name]["count"].x > 0:
                    print(f'{item.name}: {base.vars[bag.name][item.name]["count"].x}')
            print()

        print('\n=== Total items ===')
        for item in items:
            if base.vars[item.name]["count"].x > 0:
                print(f'{item.name}: {base.vars[item.name]["count"].x}')


