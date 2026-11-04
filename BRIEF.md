# Brief

## The client and the question

**The client is a fleet manager** who runs cars and vans in Great Britain, pays for their MOT tests, their repairs and their time off the road, and decides which parts are inspected before each vehicle's test.

> *Given what last year's tests found on a vehicle, which problems will its tests find this year, and is a prediction of them worth acting on?*

We answer with a memo about a product that would make this prediction for each vehicle: how well it predicts compared with two simple rules, and how a fleet manager would use it. We do not build the product.

## The question, as data

- **The prediction.** For each vehicle of every class and each year from 2019 to 2025, every **problem** recorded on any of its MOT tests that year, predicted from the problems recorded in its closest earlier year with a test and from the vehicle's details. A problem is a defect together with the way it was recorded: as a failure, a failure put right at the testing station, a minor defect or an advisory.
- **Where it goes wrong.** The prediction's errors read by defect group, the 456 groups of parts the publisher's lookup tables define, such as shock absorbers or position lamps.

## How a fleet manager would use it

For each vehicle and each problem, the model gives a probability $p$ that the vehicle's tests will record it. The memo gives a method for computing, from the fleet's own figures, $c_{\text{FP}}$, what inspecting a part that turns out fine costs, and $c_{\text{FN}}$, what missing a problem costs over finding it. A part is inspected when

$$
p \;\ge\; \tau = \frac{c_{\text{FP}}}{c_{\text{FP}} + c_{\text{FN}}}
$$

## Data and provenance

The anonymised MOT tests and results of Great Britain, published by the Department for Transport up to 2023 and by the Driver and Vehicle Standards Agency from 2023, under the Open Government Licence: every test of every vehicle class from 20 May 2018, when the current defect codes came into force, to 31 December 2025, with the defects and advisories each test recorded and the lookup tables that decode them. The files, their units and every decision taken on them are in [`DATA.md`](DATA.md).

## Scope

- **We predict problems, not test results**, and make no claim about which repair lowers the risk: repairs are not in the data.
- **Costs are not in the data.** The memo gives the method for the cut-off, and each fleet supplies its own figures.
- **Fleet vehicles cannot be told apart** from others in the data, so the model is evaluated on all vehicles.
- **One kind of model**, logistic regression, measured against two simple rules: last year's problems again, and the most frequent problems of the year.

## Deliverables

- **`REPORT.md`, the memo:** the recommendation, the evidence for it, the method for setting the cut-off, and the caveats.
- **`README.md`:** what the project found, and how to run it.
- **`DATA.md`:** every source, unit and decision about the data.
- **The repository:** the code that fetches the files, builds the tables, and trains and scores the model, regenerating every number in the memo.
