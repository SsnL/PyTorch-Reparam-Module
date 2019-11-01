import torch
import torchreparam
import unittest
import copy

torch.set_default_dtype(torch.double)


class TestMixin(object):
    @staticmethod
    def assertTensorEqual(a, b):
        return bool((a.detach() == b.detach()).all().item())

    def _test(self, module, input_shapes):
        def get_random_input():
            return tuple(torch.randn(s) for s in input_shapes)

        inp1 = get_random_input()

        ref_m = module
        ref_out = ref_m(*inp1).detach()

        reparam_m = copy.deepcopy(module)
        reparam_m = torchreparam.ReparamModule(reparam_m)
        if self.traced:
            reparam_m = reparam_m.trace(inp1)

        self.assertTensorEqual(ref_out, reparam_m(*inp1))

        def sgd(flat_p1, inp1, inp2):
            out1 = reparam_m(*inp1, flat_param=flat_p1,
                             buffers=tuple(b.clone().detach() for _, _, b in reparam_m._buffer_infos))
            l1 = (out1 * ref_out).mean()
            flat_p2 = flat_p1 - torch.autograd.grad(l1, flat_p1, create_graph=True)[0] * 0.02
            out2 = reparam_m(*inp2, flat_param=flat_p2,
                             buffers=tuple(b.clone().detach() for _, _, b in reparam_m._buffer_infos))
            return out2

        # assert that fully reparamed forward doesn't change parameter
        ref_state_dict = {k: v.detach().clone() for k, v in reparam_m.state_dict().items()}

        sgd_inp = (torch.randn_like(reparam_m.flat_param, requires_grad=True),
                   get_random_input(), get_random_input())
        sgd(*sgd_inp)

        for k, v in reparam_m.state_dict().items():
            self.assertTensorEqual(ref_state_dict[k], v)
        torch.autograd.gradcheck(sgd, sgd_inp)
        torch.autograd.gradgradcheck(sgd, sgd_inp)

    def test_conv(self):
        self._test(torch.nn.Conv2d(3, 3, 3), ((1, 3, 3, 4),))

    def test_simple_network(self):
        class MyNet(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.feature = torch.nn.Sequential(
                    torch.nn.Linear(10, 15),
                    torch.nn.LeakyReLU(0.2),
                    # torch.nn.BatchNorm1d(15),
                    torch.nn.Linear(15, 10),
                )
                self.register_buffer('target', torch.tensor(2.))

            def forward(self, x):
                out = self.feature(x)
                return out * self.target

        self._test(MyNet(), ((2, 10),))


class TestTraced(unittest.TestCase, TestMixin):
    traced = True


class TestNotTraced(unittest.TestCase, TestMixin):
    traced = False

if __name__ == '__main__':
    unittest.main()
